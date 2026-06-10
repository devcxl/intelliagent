#!/usr/bin/env python3
"""任务执行服务层。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator, Dict, Optional
from uuid import uuid4

from src.agent.react_engine import ReactEngine
from src.db import get_session_manager
from src.db.repositories import (
    ConversationRepository,
    ExecutionTraceRepository,
    MessageRepository,
    RunRepository,
)
from src.runtime import AgentRuntime


ACTIVE_RUN_STATUSES = {"pending", "running"}


class RunServiceError(Exception):
    """run 生命周期业务错误。"""

    status_code = 400
    code = "run_service_error"


class RunConflictError(RunServiceError):
    status_code = 409
    code = "run_conflict"


class RunNotFoundError(RunServiceError):
    status_code = 404
    code = "run_not_found"


class RunValidationError(RunServiceError):
    status_code = 400
    code = "run_validation_error"


class RunService:
    """统一 CLI / Web 的任务执行入口。"""

    def __init__(self, runtime: AgentRuntime, session_manager=None):
        self.runtime = runtime
        self.session_manager = session_manager or get_session_manager()
        self.run_repository = RunRepository(self.session_manager)
        self.trace_repository = ExecutionTraceRepository(self.session_manager)
        self.message_repository = MessageRepository(self.session_manager)
        self.conversation_repository = ConversationRepository(self.session_manager)

    def create_engine(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
    ) -> ReactEngine:
        return self.runtime.create_engine(
            api_key=api_key,
            model=model,
            max_iterations=max_iterations,
        )

    def run_task(
        self,
        *,
        task: str,
        max_iterations: int,
        api_key: str | None = None,
        model: str | None = None,
        conversation_id: str | None = None,
        source_run_id: str | None = None,
    ) -> Dict[str, Any]:
        return asyncio.run(
            self.run_task_async(
                task=task,
                max_iterations=max_iterations,
                api_key=api_key,
                model=model,
                conversation_id=conversation_id,
                source_run_id=source_run_id,
            )
        )

    async def run_task_async(
        self,
        *,
        task: str,
        max_iterations: int,
        api_key: str | None = None,
        model: str | None = None,
        conversation_id: str | None = None,
        source_run_id: str | None = None,
    ) -> Dict[str, Any]:
        if conversation_id is None:
            engine = self.create_engine(
                api_key=api_key,
                model=model,
                max_iterations=max_iterations,
            )
            return await engine.run_async(task, max_iterations=max_iterations)

        return await self._run_persisted_task(
            conversation_id=conversation_id,
            task=task,
            max_iterations=max_iterations,
            api_key=api_key,
            model=model,
            source_run_id=source_run_id,
        )

    async def run_task_stream(
        self,
        *,
        task: str,
        max_iterations: int,
        api_key: str | None = None,
        model: str | None = None,
        conversation_id: str | None = None,
        source_run_id: str | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if conversation_id is not None:
            async for step in self._run_persisted_task_stream(
                conversation_id=conversation_id,
                task=task,
                max_iterations=max_iterations,
                api_key=api_key,
                model=model,
                source_run_id=source_run_id,
            ):
                yield step
            return

        engine = self.create_engine(
            api_key=api_key,
            model=model,
            max_iterations=max_iterations,
        )
        async for step in engine.iter_steps(task, max_iterations=max_iterations):
            yield step

    async def cancel_run(self, run_id: str) -> bool:
        run = await self.run_repository.get(run_id)
        if run is None or run.status not in ACTIVE_RUN_STATUSES:
            return False

        updated = await self.run_repository.update_status(
            run_id,
            cancel_requested=True,
        )
        return updated is not None

    async def rerun(
        self,
        *,
        conversation_id: str,
        task: str,
        max_iterations: int,
        source_run_id: str,
        api_key: str | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        source_run = await self.run_repository.get(source_run_id)
        if source_run is None:
            raise RunNotFoundError(f"source_run_id 不存在: {source_run_id}")
        if source_run.conversation_id != conversation_id:
            raise RunValidationError("source_run_id 不属于当前会话")

        return await self.run_task_async(
            task=task,
            max_iterations=max_iterations,
            api_key=api_key,
            model=model,
            conversation_id=conversation_id,
            source_run_id=source_run_id,
        )

    async def resume(
        self,
        run_id: str,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> Dict[str, Any]:
        run = await self.run_repository.get(run_id)
        if run is None:
            raise RunNotFoundError(f"Run 不存在: {run_id}")
        if run.status not in {"cancelled", "failed"}:
            raise RunValidationError(f"Run 当前状态不支持恢复: {run.status}")

        conversation = await self.conversation_repository.get(run.conversation_id)
        if conversation is None:
            raise RunValidationError(f"Conversation 不存在: {run.conversation_id}")

        traces = await self.trace_repository.list_by_run(run_id)
        seed_observations = []
        start_iteration = max(run.current_iteration + 1, 1)
        for trace in traces:
            if trace.type != "observation":
                continue
            seed_observations.append(json.loads(trace.data))

        return await self._run_persisted_task(
            conversation_id=run.conversation_id,
            task=run.task_snapshot or conversation.task,
            max_iterations=run.max_iterations,
            api_key=api_key,
            model=model,
            existing_run_id=run_id,
            start_iteration=start_iteration,
            seed_observations=seed_observations,
            reset_state=False,
        )

    async def _run_persisted_task(
        self,
        *,
        conversation_id: str,
        task: str,
        max_iterations: int,
        api_key: str | None,
        model: str | None,
        source_run_id: str | None = None,
        existing_run_id: str | None = None,
        start_iteration: int = 1,
        seed_observations: Optional[list[Dict[str, Any]]] = None,
        reset_state: bool = True,
    ) -> Dict[str, Any]:
        engine = self.create_engine(
            api_key=api_key,
            model=model,
            max_iterations=max_iterations,
        )

        run = await self._prepare_run_record(
            conversation_id=conversation_id,
            task=task,
            max_iterations=max_iterations,
            source_run_id=source_run_id,
            existing_run_id=existing_run_id,
            start_iteration=start_iteration,
        )

        observations = list(seed_observations or [])
        last_iteration = max(start_iteration - 1, 0)
        try:
            async for event in engine.iter_steps(
                task,
                max_iterations=max_iterations,
                start_iteration=start_iteration,
                seed_observations=seed_observations,
                reset_state=reset_state,
                cancel_checker=lambda: self._is_cancel_requested(run.id),
            ):
                last_iteration = event.get("iteration", last_iteration)
                await self._persist_event(run.id, event)

                if event["type"] == "observation":
                    observations.append(event["data"])
                    continue

                if event["type"] == "answer":
                    answer = event["data"].get("answer", "")
                    await self.message_repository.create(
                        message_id=str(uuid4()),
                        conversation_id=conversation_id,
                        role="assistant",
                        content=answer,
                    )
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="completed",
                        current_iteration=last_iteration,
                    )
                    return {
                        "success": True,
                        "summary": f"任务成功完成，经过 {last_iteration} 次迭代",
                        "conversation_id": conversation_id,
                        "iterations": last_iteration,
                        "answer": answer,
                        "observations": observations,
                        "error": None,
                        "run_id": run.id,
                    }

                if event["type"] == "error":
                    error = event.get("message", "无法生成 LLM 思考")
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="failed",
                        current_iteration=max(last_iteration - 1, 0),
                        error=error,
                    )
                    return {
                        "success": False,
                        "summary": f"任务执行出错: {error}",
                        "conversation_id": conversation_id,
                        "iterations": max(last_iteration - 1, 0),
                        "answer": None,
                        "observations": observations,
                        "error": error,
                        "run_id": run.id,
                    }

                if event["type"] == "cancelled":
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="cancelled",
                        current_iteration=last_iteration,
                        error="任务已取消",
                    )
                    return {
                        "success": False,
                        "summary": f"任务已取消，执行到第 {last_iteration} 次迭代",
                        "conversation_id": conversation_id,
                        "iterations": last_iteration,
                        "answer": None,
                        "observations": observations,
                        "error": "任务已取消",
                        "run_id": run.id,
                    }

                if event["type"] == "timeout":
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="failed",
                        current_iteration=max_iterations,
                        error="达到最大迭代次数",
                    )
                    return {
                        "success": False,
                        "summary": f"达到最大迭代次数 ({max_iterations})，任务未完成",
                        "conversation_id": conversation_id,
                        "iterations": max_iterations,
                        "answer": None,
                        "observations": observations,
                        "error": "达到最大迭代次数",
                        "run_id": run.id,
                    }
        except Exception as exc:
            await self._finish_run(
                run.id,
                conversation_id=conversation_id,
                status="failed",
                current_iteration=last_iteration,
                error=str(exc),
            )
            return {
                "success": False,
                "summary": f"任务执行出错: {exc}",
                "conversation_id": conversation_id,
                "iterations": last_iteration,
                "answer": None,
                "observations": observations,
                "error": str(exc),
                "run_id": run.id,
            }

    async def _run_persisted_task_stream(
        self,
        *,
        conversation_id: str,
        task: str,
        max_iterations: int,
        api_key: str | None,
        model: str | None,
        source_run_id: str | None = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        engine = self.create_engine(
            api_key=api_key,
            model=model,
            max_iterations=max_iterations,
        )
        run = await self._prepare_run_record(
            conversation_id=conversation_id,
            task=task,
            max_iterations=max_iterations,
            source_run_id=source_run_id,
        )

        terminal_handled = False

        try:
            async for event in engine.iter_steps(
                task,
                max_iterations=max_iterations,
                cancel_checker=lambda: self._is_cancel_requested(run.id),
            ):
                await self._persist_event(run.id, event)
                if event["type"] == "answer":
                    terminal_handled = True
                    await self.message_repository.create(
                        message_id=str(uuid4()),
                        conversation_id=conversation_id,
                        role="assistant",
                        content=event["data"].get("answer", ""),
                    )
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="completed",
                        current_iteration=event.get("iteration", 0),
                    )
                elif event["type"] == "error":
                    terminal_handled = True
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="failed",
                        current_iteration=max(event.get("iteration", 1) - 1, 0),
                        error=event.get("message", "无法生成 LLM 思考"),
                    )
                elif event["type"] == "cancelled":
                    terminal_handled = True
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="cancelled",
                        current_iteration=event.get("iteration", 0),
                        error="任务已取消",
                    )
                elif event["type"] == "timeout":
                    terminal_handled = True
                    await self._finish_run(
                        run.id,
                        conversation_id=conversation_id,
                        status="failed",
                        current_iteration=max_iterations,
                        error="达到最大迭代次数",
                    )
                yield {**event, "run_id": run.id}
        except Exception as exc:
            terminal_handled = True
            await self._finish_run(
                run.id,
                conversation_id=conversation_id,
                status="failed",
                current_iteration=run.current_iteration,
                error=str(exc),
            )
            yield {
                "type": "error",
                "iteration": run.current_iteration,
                "message": str(exc),
                "run_id": run.id,
            }

        if not terminal_handled:
            await self._finish_run(
                run.id,
                conversation_id=conversation_id,
                status="failed",
                current_iteration=max_iterations,
                error="达到最大迭代次数",
            )

    async def _prepare_run_record(
        self,
        *,
        conversation_id: str,
        task: str,
        max_iterations: int,
        source_run_id: str | None = None,
        existing_run_id: str | None = None,
        start_iteration: int = 1,
    ):
        conversation = await self.conversation_repository.get(conversation_id)
        if conversation is None:
            raise RunValidationError(f"Conversation 不存在: {conversation_id}")

        if source_run_id is not None:
            source_run = await self.run_repository.get(source_run_id)
            if source_run is None:
                raise RunNotFoundError(f"source_run_id 不存在: {source_run_id}")
            if source_run.conversation_id != conversation_id:
                raise RunValidationError("source_run_id 不属于当前会话")

        if existing_run_id is None:
            active_run = await self.run_repository.get_active_by_conversation(conversation_id)
            if active_run is not None:
                raise RunConflictError(
                    f"Conversation {conversation_id} 已存在活跃 run"
                )

            run = await self.run_repository.create(
                run_id=str(uuid4()),
                conversation_id=conversation_id,
                task_snapshot=task,
                status="pending",
                max_iterations=max_iterations,
                current_iteration=max(start_iteration - 1, 0),
                source_run_id=source_run_id,
            )
            if source_run_id is None:
                await self.message_repository.create(
                    message_id=str(uuid4()),
                    conversation_id=conversation_id,
                    role="user",
                    content=task,
                )
        else:
            active_run = await self.run_repository.get_active_by_conversation(conversation_id)
            if active_run is not None and active_run.id != existing_run_id:
                raise RunConflictError(
                    f"Conversation {conversation_id} 已存在其他活跃 run"
                )

            run = await self.run_repository.get(existing_run_id)
            if run is None:
                raise RunNotFoundError(f"Run 不存在: {existing_run_id}")

        try:
            updated_run = await self.run_repository.update_status(
                run.id,
                status="running",
                current_iteration=max(start_iteration - 1, 0),
                error=None,
                cancel_requested=False,
            )
        except ValueError as exc:
            raise RunConflictError(str(exc)) from exc
        await self.conversation_repository.update(conversation_id, status="running")
        return updated_run or run

    async def _persist_event(self, run_id: str, event: Dict[str, Any]) -> None:
        event_type = event["type"]
        iteration = event.get("iteration", 0)

        if event_type in {"thought", "action", "observation", "answer", "error", "cancelled"}:
            payload = event.get("data", {})
            if event_type in {"error", "cancelled"}:
                payload = {"message": event.get("message", "")}

            await self.trace_repository.create(
                trace_id=str(uuid4()),
                run_id=run_id,
                iteration=iteration,
                trace_type=event_type,
                data=payload,
            )

        if iteration:
            await self.run_repository.update_status(
                run_id,
                current_iteration=iteration,
            )

    async def _is_cancel_requested(self, run_id: str) -> bool:
        run = await self.run_repository.get(run_id)
        return bool(run and run.cancel_requested)

    async def _finish_run(
        self,
        run_id: str,
        *,
        conversation_id: str,
        status: str,
        current_iteration: int,
        error: str | None = None,
    ) -> None:
        await self.run_repository.update_status(
            run_id,
            status=status,
            current_iteration=current_iteration,
            error=error,
            cancel_requested=False,
        )
        await self.conversation_repository.update(conversation_id, status=status)

#!/usr/bin/env python3
"""RunService — 管理 agent run 的生命周期。"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from src.core.context_manager import ContextManager
from src.db.manager import DatabaseManager


class RunService:
    """管理 run 创建、恢复、重跑、取消和持久化。"""

    def __init__(self, runtime: Any, db_manager: DatabaseManager) -> None:
        self._runtime = runtime
        self._db = db_manager

    def run_task(self, task: str, max_iterations: int = 10) -> dict[str, Any]:
        import asyncio

        return asyncio.run(self.run_task_async(task=task, max_iterations=max_iterations))

    async def run_task_async(
        self,
        task: str,
        max_iterations: int = 10,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        history_context = await self._build_history_context(conversation_id)
        engine = self._runtime.create_engine(
            api_key=None,
            model=None,
            max_iterations=max_iterations,
        )

        result = await engine.run(
            task,
            max_iterations=max_iterations,
            history_context=history_context,
        )

        if conversation_id:
            await self._db.save_message(conversation_id, "user", task)
            if result.get("answer"):
                await self._db.save_message(conversation_id, "assistant", result["answer"])

            run_id = f"run-{id(result)}"
            await self._db.create_run(
                run_id=run_id,
                conversation_id=conversation_id,
                task_snapshot=task,
                status="completed" if result["success"] else "failed",
                max_iterations=max_iterations,
                current_iteration=result.get("num_turns", 0),
            )
            result["run_id"] = run_id

        return result

    async def run_task_stream(
        self,
        task: str,
        max_iterations: int = 10,
    ) -> AsyncGenerator[dict[str, Any], None]:
        engine = self._runtime.create_engine(max_iterations=max_iterations)
        async for event in engine.iter_steps(task, max_iterations=max_iterations):
            yield event

    async def resume(self, run_id: str) -> dict[str, Any]:
        run = await self._db.get_run(run_id)
        if run is None:
            return {"success": False, "error": f"run {run_id} 不存在"}

        existing = await self._db.list_runs_by_conversation(run["conversation_id"])
        for existing_run in existing:
            if existing_run["id"] != run_id and existing_run["status"] in ("running", "pending"):
                return {"success": False, "error": f"Conversation 已存在其他活跃 run: {existing_run['id']}"}

        engine = self._runtime.create_engine(max_iterations=run.get("max_iterations", 10))
        max_iterations = run.get("max_iterations", 10)
        history_context = await self._build_history_context(run["conversation_id"])
        result = await engine.run(
            run.get("task_snapshot", ""),
            max_iterations=max_iterations,
            history_context=history_context,
        )

        await self._db.update_run(
            run_id,
            status="completed" if result["success"] else "failed",
            current_iteration=result.get("num_turns", 0),
        )
        result["run_id"] = run_id
        return result

    async def rerun(
        self,
        conversation_id: str,
        task: str,
        max_iterations: int = 10,
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        if source_run_id:
            source_run = await self._db.get_run(source_run_id)
            if source_run is None:
                return {"success": False, "error": f"源 run {source_run_id} 不存在"}
            if source_run["conversation_id"] != conversation_id:
                raise ValueError("source_run_id 不属于当前 Conversation")

        run_id = f"run-rerun-{id(task)}"
        await self._db.create_run(
            run_id=run_id,
            conversation_id=conversation_id,
            task_snapshot=task,
            status="running",
            max_iterations=max_iterations,
            source_run_id=source_run_id,
        )

        engine = self._runtime.create_engine(max_iterations=max_iterations)
        history_context = await self._build_history_context(conversation_id)
        result = await engine.run(
            task,
            max_iterations=max_iterations,
            history_context=history_context,
        )

        await self._db.update_run(
            run_id,
            status="completed" if result["success"] else "failed",
            current_iteration=result.get("num_turns", 0),
        )

        if result.get("answer"):
            await self._db.save_message(conversation_id, "assistant", result["answer"])

        result["run_id"] = run_id
        return result

    async def cancel_run(self, run_id: str) -> bool:
        return await self._db.update_run(run_id, cancel_requested=True)

    async def _build_history_context(self, conversation_id: str | None) -> str | None:
        if not conversation_id:
            return None
        history_messages = await self._db.get_messages(conversation_id)
        return ContextManager.build_history_context(history_messages)


__all__ = ["RunService"]

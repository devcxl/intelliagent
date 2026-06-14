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
        """同步执行 agent 任务（封装 run_task_async）。

        Args:
            task: 用户任务描述
            max_iterations: 最大 ReAct 迭代次数，默认 10

        Returns:
            包含 success、answer、num_turns 等字段的结果字典
        """
        import asyncio

        return asyncio.run(self.run_task_async(task=task, max_iterations=max_iterations))

    async def run_task_async(
        self,
        task: str,
        max_iterations: int = 10,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """异步执行 agent 任务，支持对话持久化。

        Args:
            task: 用户任务描述
            max_iterations: 最大 ReAct 迭代次数，默认 10
            conversation_id: 关联的对话 ID，传入时自动持久化消息和 run 记录

        Returns:
            包含 success、answer、num_turns、run_id 等字段的结果字典
        """
        history_context = await self._build_history_context(conversation_id)
        engine = await self._runtime.create_engine(
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
        """流式执行 agent 任务，逐步产出事件。

        Args:
            task: 用户任务描述
            max_iterations: 最大 ReAct 迭代次数，默认 10

        Yields:
            每个 ReAct 步骤的事件字典，包含 step、action、observation 等字段
        """
        engine = await self._runtime.create_engine(max_iterations=max_iterations)
        async for event in engine.iter_steps(task, max_iterations=max_iterations):
            yield event

    async def resume(self, run_id: str) -> dict[str, Any]:
        """恢复已存在的 run。

        检查 run 是否存在且对应 conversation 无其他活跃 run 后重新执行。

        Args:
            run_id: 要恢复的 run ID

        Returns:
            执行结果字典，失败时包含 error 字段
        """
        run = await self._db.get_run(run_id)
        if run is None:
            return {"success": False, "error": f"run {run_id} 不存在"}

        existing = await self._db.list_runs_by_conversation(run["conversation_id"])
        for existing_run in existing:
            if existing_run["id"] != run_id and existing_run["status"] in ("running", "pending"):
                return {"success": False, "error": f"Conversation 已存在其他活跃 run: {existing_run['id']}"}

        result = await self._execute_run(
            run_id=run_id,
            conversation_id=run["conversation_id"],
            task=run.get("task_snapshot", ""),
            max_iterations=run.get("max_iterations", 10),
        )
        return result

    async def rerun(
        self,
        conversation_id: str,
        task: str,
        max_iterations: int = 10,
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        """在已有对话中重新执行任务。

        可选关联源 run 用于追溯。会创建新的 run 记录并持久化结果。

        Args:
            conversation_id: 对话 ID
            task: 任务描述
            max_iterations: 最大迭代次数，默认 10
            source_run_id: 源 run ID，用于追溯关联

        Returns:
            执行结果字典

        Raises:
            ValueError: source_run_id 不属于当前 conversation 时抛出
        """
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

        result = await self._execute_run(
            run_id=run_id,
            conversation_id=conversation_id,
            task=task,
            max_iterations=max_iterations,
        )

        if result.get("answer"):
            await self._db.save_message(conversation_id, "assistant", result["answer"])

        return result

    async def _execute_run(
        self,
        run_id: str,
        conversation_id: str,
        task: str,
        max_iterations: int,
    ) -> dict[str, Any]:
        """内部执行逻辑 — 创建引擎、运行任务、更新 run 状态。

        Args:
            run_id: run 标识
            conversation_id: 对话 ID，用于加载历史上下文
            task: 任务描述
            max_iterations: 最大迭代次数

        Returns:
            包含 success、answer、num_turns、run_id 的结果字典
        """
        engine = await self._runtime.create_engine(max_iterations=max_iterations)
        history_context = await self._build_history_context(conversation_id)
        result = await engine.run(task, max_iterations=max_iterations, history_context=history_context)

        await self._db.update_run(
            run_id,
            status="completed" if result["success"] else "failed",
            current_iteration=result.get("num_turns", 0),
        )
        result["run_id"] = run_id
        return result

    async def cancel_run(self, run_id: str) -> bool:
        """请求取消正在执行的 run。

        Args:
            run_id: 要取消的 run ID

        Returns:
            True 表示取消请求已记录，False 表示操作失败
        """
        return await self._db.update_run(run_id, cancel_requested=True)

    async def _build_history_context(self, conversation_id: str | None) -> str | None:
        """从数据库加载对话历史并构建上下文。

        Args:
            conversation_id: 对话 ID，None 时返回 None

        Returns:
            格式化后的历史上下文字符串，无历史时返回 None
        """
        if not conversation_id:
            return None
        history_messages = await self._db.get_messages(conversation_id)
        return ContextManager.build_history_context(history_messages)


__all__ = ["RunService"]

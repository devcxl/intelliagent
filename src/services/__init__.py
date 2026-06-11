#!/usr/bin/env python3
"""Services 模块 — 运行服务。"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from src.db.manager import DatabaseManager


class RunService:
    """运行服务 — 管理 agent 执行的完整生命周期。

    职责：
    - 创建、恢复、重跑、取消 run
    - 持久化消息和执行轨迹
    - 流式返回执行步骤
    """

    def __init__(self, runtime: Any, db_manager: DatabaseManager) -> None:
        self._runtime = runtime
        self._db = db_manager

    # ------------------------------------------------------------------
    # 同步包装
    # ------------------------------------------------------------------
    def run_task(self, task: str, max_iterations: int = 10) -> dict[str, Any]:
        import asyncio

        return asyncio.run(self.run_task_async(task=task, max_iterations=max_iterations))

    # ------------------------------------------------------------------
    # 异步执行
    # ------------------------------------------------------------------
    async def run_task_async(
        self,
        task: str,
        max_iterations: int = 10,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        engine = self._runtime.create_engine(
            api_key=None,
            model=None,
            max_iterations=max_iterations,
        )

        result = await engine.run_async(task, max_iterations=max_iterations)

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

    # ------------------------------------------------------------------
    # 流式执行
    # ------------------------------------------------------------------
    async def run_task_stream(
        self,
        task: str,
        max_iterations: int = 10,
    ) -> AsyncGenerator[dict[str, Any], None]:
        engine = self._runtime.create_engine(max_iterations=max_iterations)
        async for event in engine.iter_steps(task):
            yield event

    # ------------------------------------------------------------------
    # 恢复 / 重跑 / 取消
    # ------------------------------------------------------------------
    async def resume(self, run_id: str) -> dict[str, Any]:
        run = await self._db.get_run(run_id)
        if run is None:
            return {"success": False, "error": f"run {run_id} 不存在"}

        existing = await self._db.list_runs_by_conversation(run["conversation_id"])
        for r in existing:
            if r["id"] != run_id and r["status"] in ("running", "pending"):
                return {"success": False, "error": f"会话已存在其他活跃 run: {r['id']}"}

        engine = self._runtime.create_engine(max_iterations=run.get("max_iterations", 10))
        result = await engine.run_async(run.get("task_snapshot", ""), max_iterations=run.get("max_iterations", 10))

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
                raise ValueError("source_run_id 不属于当前会话")

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
        result = await engine.run_async(task, max_iterations=max_iterations)

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


__all__ = ["RunService"]

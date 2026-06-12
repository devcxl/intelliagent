#!/usr/bin/env python3
"""Conversation 生命周期编排 — 创建/恢复/执行/状态更新。"""

from __future__ import annotations

import time
from typing import Any, AsyncGenerator

from src.config.settings import get_settings
from src.core.context_manager import ContextManager
from src.db.manager import DatabaseManager
from src.runtime import AgentRuntime


class ConversationOrchestrator:
    """管理 Conversation 生命周期：创建/恢复/执行/状态更新。"""

    def __init__(self, settings: Any | None = None) -> None:
        self._settings = settings or get_settings()
        db_url = self._settings.DATABASE_URL
        self._db = DatabaseManager(db_url)
        self._conversation_id: str | None = None
        self._run_id: str | None = None
        self._is_new: bool = True
        self._last_iteration: int = 0
        self._warnings: list[str] = []

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    @property
    def run_id(self) -> str | None:
        return self._run_id

    @property
    def is_new(self) -> bool:
        return self._is_new

    @property
    def warnings(self) -> list[str]:
        return self._warnings

    async def initialize(self) -> None:
        """初始化数据库。"""
        await self._db.initialize()

    async def setup_conversation(
        self,
        task: str,
        session_id: str | None = None,
        resume: bool = False,
    ) -> tuple[str, str | None]:
        """创建或恢复 Conversation，返回 (conversation_id, history_context)。"""
        self._warnings = []
        conversation_id: str

        if session_id:
            existing = await self._db.get_conversation(session_id)
            if existing is None:
                self._warnings.append(f"Conversation {session_id} 不存在，将创建新 Conversation。")
                conversation_id = session_id
                await self._db.create_conversation(conversation_id, title=task[:80], task=task)
                self._is_new = True
            else:
                conversation_id = session_id
                await self._db.update_conversation(conversation_id, status="running")
                self._is_new = False
        elif resume:
            latest = await self._db.get_latest_conversation()
            if latest:
                conversation_id = latest["id"]
                await self._db.update_conversation(conversation_id, status="running")
                self._is_new = False
            else:
                self._warnings.append("没有历史 Conversation，将创建新 Conversation。")
                conversation_id = f"conv-{int(time.time() * 1000)}"
                await self._db.create_conversation(conversation_id, title=task[:80], task=task)
                self._is_new = True
        else:
            conversation_id = f"conv-{int(time.time() * 1000)}"
            await self._db.create_conversation(conversation_id, title=task[:80], task=task)
            self._is_new = True

        self._conversation_id = conversation_id

        history_messages = await self._db.get_messages(conversation_id)
        history_context = ContextManager.build_history_context(history_messages)
        return conversation_id, history_context

    async def create_run(self, task: str) -> str:
        """创建运行记录。"""
        if not self._conversation_id:
            raise RuntimeError("Conversation 未初始化，请先调用 setup_conversation()")
        run_id = f"run-{int(time.time() * 1000)}"
        await self._db.create_run(
            run_id=run_id,
            conversation_id=self._conversation_id,
            task_snapshot=task,
            status="running",
        )
        self._run_id = run_id
        return run_id

    async def save_message(self, role: str, content: str) -> None:
        """保存消息。"""
        if self._conversation_id:
            await self._db.save_message(self._conversation_id, role, content)

    async def save_trace(
        self, seq: int, iteration: int, trace_type: str, data: dict[str, Any],
    ) -> None:
        """保存执行轨迹。"""
        if self._run_id:
            await self._db.save_trace(
                trace_id=f"trace-{self._run_id}-{seq}",
                run_id=self._run_id,
                iteration=iteration,
                trace_type=trace_type,
                data=data,
            )

    async def finalize(self, status: str = "finished") -> dict[str, Any]:
        """更新 Conversation 和 Run 状态。"""
        if self._conversation_id:
            await self._db.update_conversation(self._conversation_id, status=status)
        if self._run_id:
            await self._db.update_run(
                self._run_id,
                status="completed",
                current_iteration=self._last_iteration,
            )
        return {
            "conversation_id": self._conversation_id,
            "run_id": self._run_id,
        }

    async def list_conversations(self) -> list[dict[str, Any]]:
        """获取所有 Conversation 列表。"""
        return await self._db.list_conversations()

    async def get_message_count(self, conversation_id: str) -> int:
        """获取 Conversation 的消息数。"""
        return len(await self._db.get_messages(conversation_id))

    async def save_event_trace(self, seq: int, event: dict[str, Any]) -> str | None:
        """根据事件类型保存执行轨迹，返回 assistant_content（仅 answer 事件）。"""
        t = event["type"]
        data = event["data"]

        if t == "thought":
            await self.save_trace(seq, event["iteration"], "thought", {"content": data.get("content", "")})
        elif t == "action":
            await self.save_trace(seq, event["iteration"], "action", {"tool": data["tool"], "args": data["args"]})
        elif t == "observation":
            await self.save_trace(seq, event["iteration"], "observation", {
                "tool_name": data.get("tool_name", ""),
                "tool_args": data.get("tool_args", {}),
                "result": data.get("result", ""),
                "status": data.get("status", ""),
            })
        elif t == "answer":
            await self.save_trace(seq, event["iteration"], "answer", {"answer": data["answer"]})
            return data["answer"]
        return None

    async def execute(
        self, task: str, history_context: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行 agent run 并流式输出事件。"""
        engine = AgentRuntime(self._settings).create_engine()
        async for event in engine.iter_steps(task, history_context=history_context):
            self._last_iteration = event["iteration"]
            yield event

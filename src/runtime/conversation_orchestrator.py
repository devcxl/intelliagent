#!/usr/bin/env python3
"""Conversation 生命周期编排 — 创建/恢复/执行/状态更新。"""

from __future__ import annotations

import time
from typing import Any, AsyncGenerator, Callable, Protocol, runtime_checkable

from src.config.settings import get_settings
from src.core.constants import build_history_context
from src.db.manager import DatabaseManager
from src.runtime.agent_runtime import AgentRuntime
from src.tools.task_tools import set_task_context


@runtime_checkable
class _RuntimeProtocol(Protocol):
    async def create_engine(self) -> Any: ...
    async def stop_mcp(self) -> None: ...
    async def start_mcp(self, registry: Any = None) -> None: ...


class ConversationOrchestrator:
    """管理 Conversation 生命周期：创建/恢复/执行/状态更新。

    通过 runtime_factory 注入 AgentRuntime 创建方式，支持 CLI/Web/GUI 等
    不同调用方式使用各自的权限确认回调。
    """

    def __init__(
        self,
        settings: Any | None = None,
        runtime_factory: Callable[[], _RuntimeProtocol] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        db_url = self._settings.DATABASE_URL
        self._db = DatabaseManager(db_url)
        self._conversation_id: str | None = None
        self._is_new: bool = True
        self._warnings: list[str] = []
        self._runtime_factory = runtime_factory or AgentRuntime

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    @property
    def is_new(self) -> bool:
        return self._is_new

    @property
    def warnings(self) -> list[str]:
        return self._warnings

    async def initialize(self) -> None:
        await self._db.initialize()

    async def setup_conversation(
        self,
        task: str,
        session_id: str | None = None,
        resume: bool = False,
    ) -> tuple[str, str | None]:
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
        set_task_context(self._db, conversation_id)

        history_messages = await self._db.get_messages(conversation_id)
        history_context = build_history_context(history_messages)
        return conversation_id, history_context

    async def save_message(self, role: str, content: str) -> None:
        if self._conversation_id:
            await self._db.save_message(self._conversation_id, role, content)

    async def list_conversations(self) -> list[dict[str, Any]]:
        return await self._db.list_conversations()

    async def get_message_count(self, conversation_id: str) -> int:
        return len(await self._db.get_messages(conversation_id))

    async def execute(
        self,
        task: str,
        history_context: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        runtime = self._runtime_factory()
        engine = await runtime.create_engine()
        try:
            async for event in engine.iter_steps(task, history_context=history_context):
                yield event
        finally:
            await runtime.stop_mcp()

#!/usr/bin/env python3
"""Conversation 生命周期编排 — 创建/恢复/执行/状态更新。"""

from __future__ import annotations

import time
from typing import Any, AsyncGenerator, Callable, Protocol, runtime_checkable

from src.config.settings import get_settings
from src.core.constants import build_history_context
from src.db.engine import create_engine, create_session_factory, init_db
from src.db.repositories import (
    ConversationRepository,
    MessageRepository,
)
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
        self._engine = create_engine(db_url)
        self._session_factory = create_session_factory(self._engine)
        self._conversation_id: str | None = None
        self._is_new: bool = True
        self._warnings: list[str] = []
        self._runtime_factory = runtime_factory or AgentRuntime
        self._runtime: _RuntimeProtocol | None = None

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
        await init_db(self._engine)

    async def setup_conversation(
        self,
        task: str,
        session_id: str | None = None,
        resume: bool = False,
    ) -> tuple[str, str | None]:
        self._warnings = []
        conversation_id: str

        async with self._session_factory() as session:
            conv_repo = ConversationRepository(session)
            msg_repo = MessageRepository(session)

            if session_id:
                existing = await conv_repo.get(session_id)
                if existing is None:
                    self._warnings.append(f"Conversation {session_id} 不存在，将创建新 Conversation。")
                    conversation_id = session_id
                    await conv_repo.create(conversation_id, title=task[:80])
                    self._is_new = True
                else:
                    conversation_id = session_id
                    await conv_repo.update(conversation_id, status="running")
                    self._is_new = False
            elif resume:
                latest = await conv_repo.get_latest()
                if latest:
                    conversation_id = latest["id"]
                    await conv_repo.update(conversation_id, status="running")
                    self._is_new = False
                else:
                    self._warnings.append("没有历史 Conversation，将创建新 Conversation。")
                    conversation_id = f"conv-{int(time.time() * 1000)}"
                    await conv_repo.create(conversation_id, title=task[:80])
                    self._is_new = True
            else:
                conversation_id = f"conv-{int(time.time() * 1000)}"
                await conv_repo.create(conversation_id, title=task[:80])
                self._is_new = True

            self._conversation_id = conversation_id
            set_task_context(self._session_factory, conversation_id)

            history_messages = await msg_repo.list_by_conversation(conversation_id)
            history_context = build_history_context(history_messages)
            return conversation_id, history_context

    async def save_message(self, role: str, content: str) -> None:
        if self._conversation_id:
            async with self._session_factory() as session:
                msg_repo = MessageRepository(session)
                await msg_repo.save(self._conversation_id, role, content)

    async def reload_history_context(self) -> str | None:
        if not self._conversation_id:
            return None
        async with self._session_factory() as session:
            msg_repo = MessageRepository(session)
            messages = await msg_repo.list_by_conversation(self._conversation_id)
            return build_history_context(messages)

    async def list_conversations(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            conv_repo = ConversationRepository(session)
            return await conv_repo.list_all()

    async def get_message_count(self, conversation_id: str) -> int:
        async with self._session_factory() as session:
            msg_repo = MessageRepository(session)
            return len(await msg_repo.list_by_conversation(conversation_id))

    async def execute(
        self,
        task: str,
        history_context: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if self._runtime is None:
            self._runtime = self._runtime_factory()
        engine = await self._runtime.create_engine()
        async for event in engine.iter_steps(task, history_context=history_context):
            yield event

    async def shutdown(self) -> None:
        if self._runtime is not None:
            await self._runtime.stop_mcp()
            self._runtime = None

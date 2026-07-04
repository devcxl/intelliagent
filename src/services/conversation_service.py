"""ConversationService — 会话生命周期与消息持久化服务层。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Conversation, Message
from src.db.repositories import ConversationRepository, MessageRepository
from src.db.repositories._utils import new_uuid


class ConversationService:
    """封装 Conversation CRUD 和历史加载。

    DB engine 生命周期由 DatabaseRuntime 管理；这里只保留当前会话状态。
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._conversation_id: str | None = None
        self._is_new = True
        self._warnings: list[str] = []

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    @property
    def is_new(self) -> bool:
        return self._is_new

    @property
    def warnings(self) -> list[str]:
        return self._warnings

    async def setup_conversation(
        self,
        task: str,
        session_id: str | None = None,
        resume: bool = False,
    ) -> str:
        self._warnings = []

        async with self._session_factory() as session:
            conversation_id = await self._resolve_conversation(session, task, session_id, resume)

        self._conversation_id = conversation_id
        return conversation_id

    async def _resolve_conversation(
        self,
        session: AsyncSession,
        task: str,
        session_id: str | None,
        resume: bool,
    ) -> str:
        conv_repo = ConversationRepository(session)

        if session_id:
            return await self._setup_by_id(conv_repo, session_id, task)
        if resume:
            return await self._setup_latest(conv_repo, task)
        return await self._create_conversation(conv_repo, task)

    async def _setup_by_id(self, conv_repo: ConversationRepository, session_id: str, task: str) -> str:
        existing = await conv_repo.get(session_id)
        if existing is None:
            # 明确 session_id 时保留调用方给出的 ID，便于外部恢复同一个会话别名。
            self._warnings.append(f"Conversation {session_id} 不存在，将创建新 Conversation。")
            await conv_repo.save(Conversation(id=session_id, title=task[:80]))
            self._is_new = True
            return session_id

        await conv_repo.update(session_id, status="running")
        self._is_new = False
        return session_id

    async def _setup_latest(self, conv_repo: ConversationRepository, task: str) -> str:
        latest = await conv_repo.get_latest()
        if latest:
            conversation_id = latest.id
            await conv_repo.update(conversation_id, status="running")
            self._is_new = False
            return conversation_id

        self._warnings.append("没有历史 Conversation，将创建新 Conversation。")
        return await self._create_conversation(conv_repo, task)

    async def _create_conversation(self, conv_repo: ConversationRepository, task: str) -> str:
        conversation_id = f"conv-{uuid.uuid4()}"
        await conv_repo.save(Conversation(id=conversation_id, title=task[:80]))
        self._is_new = True
        return conversation_id

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        tool_call_id: str | None = None,
        tool_name: str | None = None,
        tool_args: str | None = None,
        tool_calls: str | None = None,
    ) -> None:
        if conversation_id is None:
            return
        async with self._session_factory() as session:
            msg_repo = MessageRepository(session)
            await msg_repo.save(
                Message(
                    id=new_uuid(),
                    conversation_id=conversation_id,
                    role=role,
                    content=content,
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    tool_calls=tool_calls,
                )
            )

    async def load_history_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        if conversation_id is None:
            return []
        async with self._session_factory() as session:
            msg_repo = MessageRepository(session)
            messages = await msg_repo.list_by_conversation(conversation_id)
        result = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role, "content": msg.content, "_msg_id": msg.id}
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.tool_calls:
                entry["tool_calls"] = json.loads(msg.tool_calls)
            if msg.tool_name:
                entry["tool_name"] = msg.tool_name
            if msg.tool_args:
                entry["tool_args"] = msg.tool_args
            result.append(entry)
        return result

    async def compact_messages(self, conversation_id: str, msg_ids: list[str], summary: str) -> None:
        if conversation_id is None:
            return
        async with self._session_factory() as session:
            msg_repo = MessageRepository(session)
            if msg_ids:
                await msg_repo.delete_by_ids(conversation_id, msg_ids)
            await msg_repo.save(
                Message(
                    id=new_uuid(),
                    conversation_id=conversation_id,
                    role="user",
                    content=summary,
                )
            )

    async def list_conversations(self) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            conv_repo = ConversationRepository(session)
            conversations = await conv_repo.list_all()
        return [self._conversation_to_dict(conversation) for conversation in conversations]

    async def get_message_count(self, conversation_id: str) -> int:
        async with self._session_factory() as session:
            msg_repo = MessageRepository(session)
            return len(await msg_repo.list_by_conversation(conversation_id))

    def _conversation_to_dict(self, conversation: Conversation) -> dict[str, Any]:
        return {
            "id": conversation.id,
            "title": conversation.title,
            "status": conversation.status,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else "",
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else "",
        }


__all__ = ["ConversationService"]

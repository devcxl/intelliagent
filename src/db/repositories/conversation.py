"""ConversationRepository — conversations 表 CRUD。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Conversation
from src.db.repositories._utils import now


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, conversation: Conversation) -> dict[str, Any]:
        self._session.add(conversation)
        await self._session.commit()
        return {"id": conversation.id, "logs": []}

    async def get(self, conversation_id: str) -> dict[str, Any] | None:
        conv = await self._session.get(Conversation, conversation_id)
        if conv is None:
            return None
        return {
            "id": conv.id,
            "title": conv.title,
            "status": conv.status,
            "created_at": conv.created_at.isoformat() if conv.created_at else "",
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else "",
            "logs": [],
        }

    async def update(
        self,
        conversation_id: str,
        title: str | None = None,
        status: str | None = None,
        logs: list[dict[str, Any]] | None = None,
    ) -> bool:
        conv = await self._session.get(Conversation, conversation_id)
        if conv is None:
            return False
        if title is not None:
            conv.title = title
        if status is not None:
            conv.status = status
        conv.updated_at = now()
        await self._session.commit()
        return True

    async def delete(self, conversation_id: str) -> bool:
        conv = await self._session.get(Conversation, conversation_id)
        if conv is not None:
            await self._session.delete(conv)
            await self._session.commit()
        return True

    async def list_all(self) -> list[dict[str, Any]]:
        result = await self._session.execute(select(Conversation).order_by(Conversation.updated_at.desc()))
        return [
            {
                "id": conv.id,
                "title": conv.title,
                "status": conv.status,
                "created_at": conv.created_at.isoformat() if conv.created_at else "",
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else "",
            }
            for conv in result.scalars()
        ]

    async def get_latest(self) -> dict[str, Any] | None:
        conversations = await self.list_all()
        return conversations[0] if conversations else None

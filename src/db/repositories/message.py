"""MessageRepository — messages 表 CRUD，ID 使用 UUID。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, message: Message) -> str:
        self._session.add(message)
        await self._session.commit()
        return message.id

    async def list_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        )
        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
            for msg in result.scalars()
        ]

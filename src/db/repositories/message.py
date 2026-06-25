"""MessageRepository — messages 表 CRUD，ID 使用 UUID。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message


class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, message: Message) -> Message:
        self._session.add(message)
        await self._session.commit()
        return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        result = await self._session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        )
        return list(result.scalars())

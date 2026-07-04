"""MessageRepository — messages 表 CRUD，ID 使用 UUID。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Message
from src.db.repositories._utils import BaseRepository


class MessageRepository(BaseRepository[Message]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Message)

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        result = await self._session.execute(
            select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        )
        return list(result.scalars())

    async def delete_by_ids(self, conversation_id: str, ids: list[str]) -> None:
        from sqlalchemy import delete

        stmt = delete(Message).where(Message.conversation_id == conversation_id).where(Message.id.in_(ids))
        await self._session.execute(stmt)
        await self._session.commit()

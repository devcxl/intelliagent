#!/usr/bin/env python3
"""Message repository。"""

from __future__ import annotations

from sqlalchemy import select

from src.db.models import Message
from src.db.session import DatabaseSessionManager


class MessageRepository:
    def __init__(self, session_manager: DatabaseSessionManager):
        self.session_manager = session_manager

    async def create(
        self,
        *,
        message_id: str,
        conversation_id: str,
        role: str,
        content: str,
    ) -> Message:
        async with self.session_manager.session() as session:
            message = Message(
                id=message_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
            )
            session.add(message)
            await session.commit()
            await session.refresh(message)
            return message

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        async with self.session_manager.session() as session:
            result = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
            )
            return list(result.scalars().all())

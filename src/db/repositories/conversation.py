#!/usr/bin/env python3
"""Conversation repository。"""

from __future__ import annotations

from sqlalchemy import select

from src.db.models import Conversation
from src.db.session import DatabaseSessionManager, utcnow


class ConversationRepository:
    def __init__(self, session_manager: DatabaseSessionManager):
        self.session_manager = session_manager

    async def create(
        self,
        *,
        conversation_id: str,
        user_id: str,
        title: str,
        task: str,
        status: str,
    ) -> Conversation:
        async with self.session_manager.session() as session:
            conversation = Conversation(
                id=conversation_id,
                user_id=user_id,
                title=title,
                task=task,
                status=status,
            )
            session.add(conversation)
            await session.commit()
            await session.refresh(conversation)
            return conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        async with self.session_manager.session() as session:
            return await session.get(Conversation, conversation_id)

    async def list_all(self) -> list[Conversation]:
        async with self.session_manager.session() as session:
            result = await session.execute(
                select(Conversation).order_by(Conversation.updated_at.desc())
            )
            return list(result.scalars().all())

    async def update(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        task: str | None = None,
        status: str | None = None,
    ) -> Conversation | None:
        async with self.session_manager.session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                return None

            if title is not None:
                conversation.title = title
            if task is not None:
                conversation.task = task
            if status is not None:
                conversation.status = status
            conversation.updated_at = utcnow()

            await session.commit()
            await session.refresh(conversation)
            return conversation

    async def delete(self, conversation_id: str) -> bool:
        async with self.session_manager.session() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                return False

            await session.delete(conversation)
            await session.commit()
            return True

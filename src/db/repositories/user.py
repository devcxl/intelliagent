#!/usr/bin/env python3
"""User repository。"""

from __future__ import annotations

from sqlalchemy import select

from src.db.models import User
from src.db.session import DatabaseSessionManager


class UserRepository:
    def __init__(self, session_manager: DatabaseSessionManager):
        self.session_manager = session_manager

    async def get_by_id(self, user_id: str) -> User | None:
        async with self.session_manager.session() as session:
            return await session.get(User, user_id)

    async def get_or_create_local_user(self) -> User:
        async with self.session_manager.session() as session:
            user = await session.get(User, "local")
            if user is not None:
                return user

            user = User(id="local", username="anonymous")
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user

    async def get_by_username(self, username: str) -> User | None:
        async with self.session_manager.session() as session:
            result = await session.execute(select(User).where(User.username == username))
            return result.scalar_one_or_none()

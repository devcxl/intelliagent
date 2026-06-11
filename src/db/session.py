#!/usr/bin/env python3
"""数据库引擎与会话管理。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.config import get_settings


def build_async_database_url(database_url: str) -> str:
    """将异步 URL 转成 Alembic 可用的同步 URL。"""
    if database_url.startswith("sqlite+aiosqlite:///"):
        return database_url.replace("sqlite+aiosqlite:///", "sqlite:///", 1)
    return database_url


class Base(DeclarativeBase):
    """ORM Base。"""


def utcnow() -> datetime:
    """返回兼容 SQLAlchemy 默认值的朴素 UTC 时间。"""
    return datetime.now(UTC).replace(tzinfo=None)


class DatabaseSessionManager:
    """管理异步 engine 与 session factory。"""

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or get_settings().DATABASE_URL
        self.async_database_url = build_async_database_url(self.database_url)
        self.engine = create_async_engine(self.async_database_url)
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """提供一个异步数据库会话。"""
        async with self.session_factory() as session:
            yield session

    async def create_all(self) -> None:
        """根据当前 ORM 元数据创建表。"""
        import src.db.models  # noqa: F401  # 确保模型已注册到 Base.metadata

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        """释放 engine 连接。"""
        await self.engine.dispose()


@lru_cache(maxsize=1)
def get_session_manager() -> DatabaseSessionManager:
    """获取默认数据库会话管理器。"""
    return DatabaseSessionManager()


def clear_session_manager_cache() -> None:
    """测试场景清理会话管理器缓存。"""
    get_session_manager.cache_clear()

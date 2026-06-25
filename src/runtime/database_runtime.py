"""DatabaseRuntime — 管理数据库 engine 和 session factory 生命周期。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.db.engine import create_engine, create_session_factory, init_db


class DatabaseRuntime:
    """Runtime 级数据库基础设施，隔离 engine/session 创建细节。"""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def initialize(self) -> None:
        await init_db(self.get_engine())

    async def shutdown(self) -> None:
        if self._engine is not None:
            # aiosqlite 使用后台线程，测试和 CLI 退出时都必须显式释放。
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    def get_engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_engine(self._database_url)
        return self._engine

    def get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = create_session_factory(self.get_engine())
        return self._session_factory


__all__ = ["DatabaseRuntime"]

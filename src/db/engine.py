"""异步 SQLAlchemy engine + session factory + 路径解析。"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base


def resolve_sqlite_database_path(database_url: str) -> Path:
    """将 SQLite URL 解析为绝对路径。

    规则：
    - sqlite:///relative/path → CWD / relative/path
    - sqlite:////absolute/path → /absolute/path
    - 非 sqlite:// 前缀 → 抛出 ValueError

    Args:
        database_url: SQLite 连接 URL（必须以 "sqlite:///" 开头）。

    Returns:
        解析后的绝对路径。

    Raises:
        ValueError: URL 不以 "sqlite:///" 开头时抛出。
    """
    if not database_url.startswith("sqlite:///"):
        raise ValueError(f"不支持的数据库 URL 类型: {database_url}")

    path_part = database_url[len("sqlite:///") :]

    # Windows 风格路径处理（如 sqlite:///C:/path）
    if len(path_part) > 2 and path_part[1] == ":":
        return Path(path_part)

    # 绝对路径：sqlite:////tmp/db → /tmp/db
    if path_part.startswith("/"):
        return Path(path_part)

    # 相对路径：sqlite:///data/db → CWD/data/db
    return Path.cwd() / path_part


def create_engine(db_url: str, **kwargs):
    """创建异步 engine，自动处理 sqlite URL 和目录创建。

    Args:
        db_url: 数据库 URL，如 "sqlite:///data/intelliagent.db" 或纯路径
        **kwargs: 传给 create_async_engine 的额外参数

    Returns:
        AsyncEngine 实例
    """
    # 纯路径 → 转 sqlite URL
    if not db_url.startswith("sqlite"):
        db_url = f"sqlite+aiosqlite:///{db_url}"
    elif db_url.startswith("sqlite:///"):
        db_url = db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    # 确保目录存在
    path_part = db_url.split("///")[-1]
    db_dir = os.path.dirname(path_part)
    if db_dir and not db_dir.startswith("/"):
        db_dir = str(Path.cwd() / db_dir)
    if db_dir:
        Path(db_dir).mkdir(parents=True, exist_ok=True)

    return create_async_engine(db_url, **kwargs)


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """创建 async session factory。"""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db(engine) -> None:
    """创建所有表。"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

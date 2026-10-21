"""storage 插件的 SQLAlchemy 模型：entries 表承载一切记录（append-only）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    """created_at 以 UTC naive 存储（SQLite DATETIME 不保留时区）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """storage 插件的 ORM 基类。"""


class EntryRow(Base):
    """一条 append-only 记录：message / compaction / run / run_status 都是 entry。

    parent_id 自引用形成链/树（pi 的 parentId 语义，ADR 0010）；表上挂触发器拒绝 UPDATE/DELETE。
    """

    __tablename__ = "entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String, ForeignKey("entries.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


APPEND_ONLY_TRIGGER_STATEMENTS: tuple[str, ...] = (
    "CREATE TRIGGER IF NOT EXISTS entries_reject_update BEFORE UPDATE ON entries "
    "BEGIN SELECT RAISE(ABORT, 'entries is append-only: UPDATE is not allowed'); END",
    "CREATE TRIGGER IF NOT EXISTS entries_reject_delete BEFORE DELETE ON entries "
    "BEGIN SELECT RAISE(ABORT, 'entries is append-only: DELETE is not allowed'); END",
)

#!/usr/bin/env python3
"""Run ORM 模型。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base, utcnow


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index(
            "ux_runs_single_active",
            "conversation_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    task_snapshot: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow,
        onupdate=utcnow,
    )

    conversation = relationship("Conversation", back_populates="runs")
    execution_traces = relationship(
        "ExecutionTrace",
        back_populates="run",
        cascade="all, delete-orphan",
    )

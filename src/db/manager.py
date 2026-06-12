#!/usr/bin/env python3
"""SQLite 数据库管理器 — Facade，委托给各仓储类。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.db.repositories import (
    ConversationRepository,
    MessageRepository,
    RunRepository,
    TraceRepository,
)


class DatabaseManager:
    """Facade — 向后兼容，委托给各仓储。

    管理核心表：
    - users: 用户信息
    - conversations: Conversation 信息
    - runs: Run 记录（一次 run = 一次 agent 执行）
    - messages: Message 历史
    - execution_traces: Trace 轨迹（thought/action/observation/answer）
    """

    def __init__(self, db_path: str) -> None:
        if db_path.startswith("sqlite:///"):
            db_path = db_path[len("sqlite:///") :]
        self.db_path = db_path
        self.conversations = ConversationRepository(db_path)
        self.messages = MessageRepository(db_path)
        self.runs = RunRepository(db_path)
        self.traces = TraceRepository(db_path)

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """创建数据库文件及所有核心表。"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)

        import sqlite3

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA_SQL)

    # ------------------------------------------------------------------
    # Conversation CRUD（委托）
    # ------------------------------------------------------------------
    async def create_conversation(
        self,
        conversation_id: str,
        title: str = "",
        task: str = "",
        status: str = "idle",
    ) -> dict[str, Any]:
        return await self.conversations.create(conversation_id, title, task, status)

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        return await self.conversations.get(conversation_id)

    async def update_conversation(
        self,
        conversation_id: str,
        title: str | None = None,
        status: str | None = None,
        logs: list[dict[str, Any]] | None = None,
    ) -> bool:
        return await self.conversations.update(conversation_id, title, status, logs)

    async def delete_conversation(self, conversation_id: str) -> bool:
        return await self.conversations.delete(conversation_id)

    async def list_conversations(self) -> list[dict[str, Any]]:
        return await self.conversations.list_all()

    # ------------------------------------------------------------------
    # 消息（Message）CRUD（委托）
    # ------------------------------------------------------------------
    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> str:
        return await self.messages.save(conversation_id, role, content)

    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        return await self.messages.list_by_conversation(conversation_id)

    # ------------------------------------------------------------------
    # 运行记录（Run）CRUD（委托）
    # ------------------------------------------------------------------
    async def create_run(
        self,
        run_id: str,
        conversation_id: str,
        task_snapshot: str,
        status: str = "pending",
        max_iterations: int = 10,
        current_iteration: int = 0,
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        return await self.runs.create(
            run_id,
            conversation_id,
            task_snapshot,
            status,
            max_iterations,
            current_iteration,
            source_run_id,
        )

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        return await self.runs.get(run_id)

    async def update_run(
        self,
        run_id: str,
        status: str | None = None,
        current_iteration: int | None = None,
        cancel_requested: bool | None = None,
    ) -> bool:
        return await self.runs.update(run_id, status, current_iteration, cancel_requested)

    async def list_runs_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        return await self.runs.list_by_conversation(conversation_id)

    # ------------------------------------------------------------------
    # 执行轨迹（ExecutionTrace）CRUD（委托）
    # ------------------------------------------------------------------
    async def save_trace(
        self,
        trace_id: str,
        run_id: str,
        iteration: int,
        trace_type: str,
        data: dict[str, Any],
    ) -> str:
        return await self.traces.save(trace_id, run_id, iteration, trace_type, data)

    async def list_traces_by_run(self, run_id: str) -> list[dict[str, Any]]:
        return await self.traces.list_by_run(run_id)

    # ------------------------------------------------------------------
    # 便捷查询
    # ------------------------------------------------------------------
    async def get_latest_conversation(self) -> dict[str, Any] | None:
        return await self.conversations.get_latest()


# ======================================================================
# SQL Schema
# ======================================================================
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    task TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    task_snapshot TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    max_iterations INTEGER NOT NULL DEFAULT 10,
    current_iteration INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    source_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_call_id TEXT,
    tool_name TEXT,
    tool_args TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE IF NOT EXISTS execution_traces (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    iteration INTEGER NOT NULL DEFAULT 0,
    trace_type TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
"""


# ======================================================================
# 工具函数
# ======================================================================
def resolve_sqlite_database_path(database_url: str) -> Path:
    """将 SQLite URL 解析为绝对路径。

    规则：
    - sqlite:///relative/path → CWD / relative/path
    - sqlite:////absolute/path → /absolute/path
    - 非 sqlite:// 前缀 → 抛出 ValueError
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

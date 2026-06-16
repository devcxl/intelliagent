#!/usr/bin/env python3
"""SQLite 数据库管理器 — Facade，委托给各仓储类。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.db.repositories import (
    ConversationRepository,
    MessageRepository,
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

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """创建数据库文件及所有核心表。

        确保数据库目录存在，然后执行建表 SQL 创建 users、conversations、
        runs、messages、execution_traces 五张表。
        """
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
        """创建新 Conversation。

        Args:
            conversation_id: Conversation 唯一 ID。
            title: 标题，默认为空字符串。
            task: 任务描述，默认为空字符串。
            status: 初始状态，默认 "idle"。

        Returns:
            包含 id 和 logs 字段的字典。
        """
        return await self.conversations.create(conversation_id, title, task, status)

    async def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        """获取单个 Conversation。

        Args:
            conversation_id: Conversation ID。

        Returns:
            Conversation 字典，不存在时返回 None。
        """
        return await self.conversations.get(conversation_id)

    async def update_conversation(
        self,
        conversation_id: str,
        title: str | None = None,
        status: str | None = None,
        logs: list[dict[str, Any]] | None = None,
    ) -> bool:
        """更新 Conversation 信息。

        Args:
            conversation_id: Conversation ID。
            title: 新标题，None 表示不更新。
            status: 新状态，None 表示不更新。
            logs: 日志列表（当前未持久化到数据库），None 表示不更新。

        Returns:
            始终返回 True。
        """
        return await self.conversations.update(conversation_id, title, status, logs)

    async def delete_conversation(self, conversation_id: str) -> bool:
        """删除 Conversation 及关联的 runs、messages、traces（级联删除）。

        Args:
            conversation_id: 要删除的 Conversation ID。

        Returns:
            始终返回 True。
        """
        return await self.conversations.delete(conversation_id)

    async def list_conversations(self) -> list[dict[str, Any]]:
        """获取所有 Conversation 列表，按更新时间降序。

        Returns:
            Conversation 字典列表，按 updated_at 降序排列。
        """
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
        """保存一条消息到指定 Conversation。

        Args:
            conversation_id: 目标 Conversation ID。
            role: 消息角色（如 "user"、"assistant"、"system"）。
            content: 消息正文。

        Returns:
            新生成的消息 ID。
        """
        return await self.messages.save(conversation_id, role, content)

    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取指定 Conversation 的所有消息。

        Args:
            conversation_id: 目标 Conversation ID。

        Returns:
            消息列表，按创建时间升序排列。
        """
        return await self.messages.list_by_conversation(conversation_id)

    # ------------------------------------------------------------------
    # 便捷查询
    # ------------------------------------------------------------------
    async def get_latest_conversation(self) -> dict[str, Any] | None:
        return await self.conversations.get_latest()


# ======================================================================
# SQL Schema
# ======================================================================
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    task TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
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

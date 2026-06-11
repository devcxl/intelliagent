#!/usr/bin/env python3
"""SQLite 数据库管理器 — 负责会话、消息、运行记录的持久化。"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DatabaseManager:
    """SQLite 数据库管理器。

    管理核心表：
    - users: 用户信息
    - conversations: 会话（session）信息
    - runs: 运行记录（一次 run = 一次 agent 执行）
    - messages: 消息历史
    - execution_traces: 执行轨迹（thought/action/observation/answer）
    """

    def __init__(self, db_path: str) -> None:
        if db_path.startswith("sqlite:///"):
            db_path = db_path[len("sqlite:///"):]
        self.db_path = db_path

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    async def initialize(self) -> None:
        """创建数据库文件及所有核心表。"""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            Path(db_dir).mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(_SCHEMA_SQL)

    # ------------------------------------------------------------------
    # 会话（Conversation）CRUD
    # ------------------------------------------------------------------
    async def create_session(
        self,
        session_id: str,
        title: str = "",
        task: str = "",
        status: str = "idle",
    ) -> dict[str, Any]:
        """创建新会话。"""
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO conversations (id, title, task, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (session_id, title, task, status, now, now),
            )
        return {"id": session_id, "logs": []}

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """获取单个会话。"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, title, task, status, created_at, updated_at FROM conversations WHERE id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "title": row[1],
            "task": row[2],
            "status": row[3],
            "created_at": row[4],
            "updated_at": row[5],
            "logs": [],
        }

    async def update_session(
        self,
        session_id: str,
        title: str | None = None,
        status: str | None = None,
        logs: list[dict[str, Any]] | None = None,
    ) -> bool:
        """更新会话信息。"""
        now = _now()
        fields = []
        values: list[Any] = []

        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if status is not None:
            fields.append("status = ?")
            values.append(status)

        fields.append("updated_at = ?")
        values.append(now)
        values.append(session_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?",
                values,
            )
        return True

    async def delete_session(self, session_id: str) -> bool:
        """删除会话及关联数据。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM conversations WHERE id = ?", (session_id,))
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (session_id,))
        return True

    async def get_all_sessions(self) -> list[dict[str, Any]]:
        """获取所有会话列表。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, title, task, status, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "task": r[2],
                "status": r[3],
                "created_at": r[4],
                "updated_at": r[5],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 消息（Message）CRUD
    # ------------------------------------------------------------------
    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> str:
        """保存一条消息，返回消息 ID。"""
        msg_id = f"msg-{_now_ts()}-{hash(content) % 10000}"
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (msg_id, conversation_id, role, content, now),
            )
        return msg_id

    async def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取某个会话的所有消息，按创建时间升序。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 运行记录（Run）CRUD
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
        """创建运行记录。"""
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO runs (id, conversation_id, task_snapshot, status, max_iterations,
                                    current_iteration, source_run_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, conversation_id, task_snapshot, status, max_iterations,
                 current_iteration, source_run_id, now, now),
            )
        return {"id": run_id}

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        """获取运行记录。"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT id, conversation_id, task_snapshot, status, max_iterations,
                          current_iteration, cancel_requested, source_run_id, created_at, updated_at
                   FROM runs WHERE id = ?""",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "conversation_id": row[1],
            "task_snapshot": row[2],
            "status": row[3],
            "max_iterations": row[4],
            "current_iteration": row[5],
            "cancel_requested": bool(row[6]) if row[6] else False,
            "source_run_id": row[7],
            "created_at": row[8],
            "updated_at": row[9],
        }

    async def update_run(
        self,
        run_id: str,
        status: str | None = None,
        current_iteration: int | None = None,
        cancel_requested: bool | None = None,
    ) -> bool:
        """更新运行记录。"""
        fields = ["updated_at = ?"]
        values: list[Any] = [_now()]

        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if current_iteration is not None:
            fields.append("current_iteration = ?")
            values.append(current_iteration)
        if cancel_requested is not None:
            fields.append("cancel_requested = ?")
            values.append(1 if cancel_requested else 0)

        values.append(run_id)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE runs SET {', '.join(fields)} WHERE id = ?",
                values,
            )
        return True

    async def list_runs_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取某个会话的所有运行记录。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT id, conversation_id, task_snapshot, status, max_iterations,
                          current_iteration, cancel_requested, source_run_id, created_at, updated_at
                   FROM runs WHERE conversation_id = ? ORDER BY created_at DESC""",
                (conversation_id,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "conversation_id": r[1],
                "task_snapshot": r[2],
                "status": r[3],
                "max_iterations": r[4],
                "current_iteration": r[5],
                "cancel_requested": bool(r[6]) if r[6] else False,
                "source_run_id": r[7],
                "created_at": r[8],
                "updated_at": r[9],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 执行轨迹（ExecutionTrace）CRUD
    # ------------------------------------------------------------------
    async def save_trace(
        self,
        trace_id: str,
        run_id: str,
        iteration: int,
        trace_type: str,
        data: dict[str, Any],
    ) -> str:
        """保存一条执行轨迹。"""
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO execution_traces (id, run_id, iteration, trace_type, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (trace_id, run_id, iteration, trace_type, json.dumps(data, ensure_ascii=False), now),
            )
        return trace_id

    async def list_traces_by_run(self, run_id: str) -> list[dict[str, Any]]:
        """获取某个运行记录的所有执行轨迹。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, run_id, iteration, trace_type, data, created_at FROM execution_traces WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "run_id": r[1],
                "iteration": r[2],
                "type": r[3],
                "data": json.loads(r[4]) if r[4] else {},
                "created_at": r[5],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # 便捷查询
    # ------------------------------------------------------------------
    async def get_latest_session(self) -> dict[str, Any] | None:
        """获取最近更新的会话。"""
        all_sessions = await self.get_all_sessions()
        return all_sessions[0] if all_sessions else None


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
# 内部工具函数
# ======================================================================
def _now() -> str:
    """返回 ISO 格式的当前时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    """返回当前时间戳（毫秒）。"""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def resolve_sqlite_database_path(database_url: str) -> Path:
    """将 SQLite URL 解析为绝对路径。

    规则：
    - sqlite:///relative/path → CWD / relative/path
    - sqlite:////absolute/path → /absolute/path
    - 非 sqlite:// 前缀 → 抛出 ValueError
    """
    if not database_url.startswith("sqlite:///"):
        raise ValueError(f"不支持的数据库 URL 类型: {database_url}")

    path_part = database_url[len("sqlite:///"):]

    # Windows 风格路径处理（如 sqlite:///C:/path）
    if len(path_part) > 2 and path_part[1] == ":":
        return Path(path_part)

    # 绝对路径：sqlite:////tmp/db → /tmp/db
    if path_part.startswith("/"):
        return Path(path_part)

    # 相对路径：sqlite:///data/db → CWD/data/db
    return Path.cwd() / path_part

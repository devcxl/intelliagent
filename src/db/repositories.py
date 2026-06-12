#!/usr/bin/env python3
"""独立仓储类 — 每张表一个仓储，职责单一。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


# ======================================================================
# 内部工具函数
# ======================================================================
def _now() -> str:
    """返回 ISO 格式的当前时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    """返回当前时间戳（毫秒）。"""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# ======================================================================
# ConversationRepository
# ======================================================================
class ConversationRepository:
    """conversations 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def create(
        self,
        conversation_id: str,
        title: str = "",
        task: str = "",
        status: str = "idle",
    ) -> dict[str, Any]:
        """创建新 Conversation。"""
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO conversations (id, title, task, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (conversation_id, title, task, status, now, now),
            )
        return {"id": conversation_id, "logs": []}

    async def get(self, conversation_id: str) -> dict[str, Any] | None:
        """获取单个 Conversation。"""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, title, task, status, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
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

    async def update(
        self,
        conversation_id: str,
        title: str | None = None,
        status: str | None = None,
        logs: list[dict[str, Any]] | None = None,
    ) -> bool:
        """更新 Conversation 信息。"""
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
        values.append(conversation_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE conversations SET {', '.join(fields)} WHERE id = ?",
                values,
            )
        return True

    async def delete(self, conversation_id: str) -> bool:
        """删除 Conversation 及关联的 runs、messages、traces（级联删除）。"""
        with sqlite3.connect(self.db_path) as conn:
            run_rows = conn.execute(
                "SELECT id FROM runs WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchall()
            for (run_id,) in run_rows:
                conn.execute("DELETE FROM execution_traces WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM runs WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return True

    async def list_all(self) -> list[dict[str, Any]]:
        """获取所有 Conversation 列表，按更新时间降序。"""
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

    async def get_latest(self) -> dict[str, Any] | None:
        """获取最近更新的 Conversation。"""
        conversations = await self.list_all()
        return conversations[0] if conversations else None


# ======================================================================
# MessageRepository
# ======================================================================
class MessageRepository:
    """messages 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def save(
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

    async def list_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取某个 Conversation 的所有消息，按创建时间升序。"""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [
            {"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]}
            for r in rows
        ]


# ======================================================================
# RunRepository
# ======================================================================
class RunRepository:
    """runs 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def create(
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

    async def get(self, run_id: str) -> dict[str, Any] | None:
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

    async def update(
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

    async def list_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取某个 Conversation 的所有 Run 记录，按创建时间降序。"""
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


# ======================================================================
# TraceRepository
# ======================================================================
class TraceRepository:
    """execution_traces 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def save(
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

    async def list_by_run(self, run_id: str) -> list[dict[str, Any]]:
        """获取某个运行记录的所有执行轨迹，按创建时间升序。"""
        with sqlite3.connect(self.db_path) as conn:
            sql = (
                "SELECT id, run_id, iteration, trace_type, data, created_at"
                " FROM execution_traces WHERE run_id = ? ORDER BY created_at ASC"
            )
            rows = conn.execute(sql, (run_id,)).fetchall()
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

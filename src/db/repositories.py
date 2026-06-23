#!/usr/bin/env python3
"""独立仓储类 — 每张表一个仓储，职责单一。"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any


# ======================================================================
# 内部工具函数
# ======================================================================
def _now() -> str:
    """返回 ISO 格式的当前 UTC 时间字符串。

    Returns:
        格式为 "YYYY-MM-DDTHH:MM:SS.ffffff+00:00" 的时间字符串。
    """
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> int:
    """返回当前 UTC 时间戳（毫秒）。

    Returns:
        自 Unix 纪元以来的毫秒数。
    """
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# 消息 ID 生成：线程安全计数器 + 时间戳
# 保证同一毫秒内不碰撞，且格式确定可复现
_msg_id_counter = 0
_msg_id_lock = threading.Lock()


def _next_msg_id() -> str:
    """生成下一条消息的唯一 ID。

    格式为 "msg-{毫秒时间戳}-{递增序号}"，线程安全，保证同一毫秒内不碰撞。

    Returns:
        格式为 "msg-{ts}-{seq}" 的唯一消息 ID。
    """
    global _msg_id_counter
    with _msg_id_lock:
        _msg_id_counter += 1
        return f"msg-{_now_ts()}-{_msg_id_counter:04d}"


# ======================================================================
# ConversationRepository
# ======================================================================
class ConversationRepository:
    """conversations 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        """初始化 Conversation 仓储。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self.db_path = db_path

    async def create(
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
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO conversations (id, title, task, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (conversation_id, title, task, status, now, now),
            )
        return {"id": conversation_id, "logs": []}

    async def get(self, conversation_id: str) -> dict[str, Any] | None:
        """获取单个 Conversation。

        Args:
            conversation_id: Conversation ID。

        Returns:
            Conversation 字典，不存在时返回 None。
        """
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
        """更新 Conversation 信息。

        Args:
            conversation_id: Conversation ID。
            title: 新标题，None 表示不更新。
            status: 新状态，None 表示不更新。
            logs: 日志列表（当前未持久化到数据库），None 表示不更新。

        Returns:
            始终返回 True。
        """
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
        """删除 Conversation 及关联的 messages 和 tasks。"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM tasks WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        return True

    async def list_all(self) -> list[dict[str, Any]]:
        """获取所有 Conversation 列表，按更新时间降序。

        Returns:
            Conversation 字典列表，按 updated_at 降序排列。
        """
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
        """获取最近更新的 Conversation。

        Returns:
            最近更新的 Conversation 字典，无记录时返回 None。
        """
        conversations = await self.list_all()
        return conversations[0] if conversations else None


# ======================================================================
# MessageRepository
# ======================================================================
class MessageRepository:
    """messages 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        """初始化 Message 仓储。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self.db_path = db_path

    async def save(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> str:
        """保存一条消息。

        Args:
            conversation_id: 目标 Conversation ID。
            role: 消息角色（如 "user"、"assistant"、"system"）。
            content: 消息正文。

        Returns:
            新生成的消息 ID。
        """
        msg_id = _next_msg_id()
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO messages (id, conversation_id, role, content, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (msg_id, conversation_id, role, content, now),
            )
        return msg_id

    async def list_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取某个 Conversation 的所有消息。

        Args:
            conversation_id: 目标 Conversation ID。

        Returns:
            消息列表，按创建时间升序排列。
        """
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [{"id": r[0], "role": r[1], "content": r[2], "created_at": r[3]} for r in rows]


# 任务 ID 生成
_task_id_counter = 0
_task_id_lock = threading.Lock()


def _next_task_id() -> str:
    """生成下一条任务的唯一 ID。"""
    global _task_id_counter
    with _task_id_lock:
        _task_id_counter += 1
        return f"task-{_now_ts()}-{_task_id_counter:04d}"


# ======================================================================
# TaskRepository
# ======================================================================
class TaskRepository:
    """tasks 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def add(
        self,
        conversation_id: str,
        title: str,
        content: str = "",
        parent_id: str | None = None,
        priority: str = "medium",
        sort_order: int = 0,
    ) -> dict[str, Any]:
        task_id = _next_task_id()
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO tasks (id, conversation_id, title, content, parent_id, status, priority,
                   sort_order, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (task_id, conversation_id, title, content, parent_id, priority, sort_order, now, now),
            )
        return {"id": task_id, "status": "pending"}

    async def get(self, task_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id, conversation_id, title, content, parent_id, status, priority, "
                "sort_order, created_at, updated_at, completed_at FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0], "conversation_id": row[1], "title": row[2],
            "content": row[3], "parent_id": row[4], "status": row[5],
            "priority": row[6], "sort_order": row[7],
            "created_at": row[8], "updated_at": row[9], "completed_at": row[10],
        }

    async def list_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, conversation_id, title, content, parent_id, status, priority, "
                "sort_order, created_at, updated_at, completed_at FROM tasks "
                "WHERE conversation_id = ? ORDER BY sort_order ASC, created_at ASC",
                (conversation_id,),
            ).fetchall()
        return [
            {
                "id": r[0], "conversation_id": r[1], "title": r[2],
                "content": r[3], "parent_id": r[4], "status": r[5],
                "priority": r[6], "sort_order": r[7],
                "created_at": r[8], "updated_at": r[9], "completed_at": r[10],
            }
            for r in rows
        ]

    async def update(
        self,
        task_id: str,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        sort_order: int | None = None,
    ) -> bool:
        now = _now()
        fields = []
        values: list[Any] = []

        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if content is not None:
            fields.append("content = ?")
            values.append(content)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
            if status == "completed":
                fields.append("completed_at = ?")
                values.append(now)
        if priority is not None:
            fields.append("priority = ?")
            values.append(priority)
        if sort_order is not None:
            fields.append("sort_order = ?")
            values.append(sort_order)

        fields.append("updated_at = ?")
        values.append(now)
        values.append(task_id)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE tasks SET {', '.join(fields)} WHERE id = ?",
                values,
            )
        return True

    async def delete_by_conversation(self, conversation_id: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM tasks WHERE conversation_id = ?", (conversation_id,))

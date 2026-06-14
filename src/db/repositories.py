#!/usr/bin/env python3
"""独立仓储类 — 每张表一个仓储，职责单一。"""

from __future__ import annotations

import json
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
        """删除 Conversation 及关联的 runs、messages、traces（级联删除）。

        Args:
            conversation_id: 要删除的 Conversation ID。

        Returns:
            始终返回 True。
        """
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


# ======================================================================
# RunRepository
# ======================================================================
class RunRepository:
    """runs 表 CRUD。"""

    def __init__(self, db_path: str) -> None:
        """初始化 Run 仓储。

        Args:
            db_path: SQLite 数据库文件路径。
        """
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
        """创建一条新的运行记录。

        Args:
            run_id: 运行记录 ID。
            conversation_id: 所属 Conversation ID。
            task_snapshot: 任务快照（JSON 字符串）。
            status: 初始状态，默认 "pending"。
            max_iterations: 最大迭代次数。
            current_iteration: 当前迭代次数。
            source_run_id: 来源运行记录 ID（用于 fork 场景）。

        Returns:
            包含 id 字段的字典。
        """
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO runs (id, conversation_id, task_snapshot, status, max_iterations,
                                    current_iteration, source_run_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    conversation_id,
                    task_snapshot,
                    status,
                    max_iterations,
                    current_iteration,
                    source_run_id,
                    now,
                    now,
                ),
            )
        return {"id": run_id}

    async def get(self, run_id: str) -> dict[str, Any] | None:
        """获取单条运行记录。

        Args:
            run_id: 运行记录 ID。

        Returns:
            运行记录字典，不存在时返回 None。
        """
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
        """更新运行记录的状态、迭代次数或取消标记。

        Args:
            run_id: 运行记录 ID。
            status: 新状态（如 "running"、"completed"），None 表示不更新。
            current_iteration: 当前迭代次数，None 表示不更新。
            cancel_requested: 是否请求取消，None 表示不更新。

        Returns:
            始终返回 True。
        """
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
        """获取某个 Conversation 的所有 Run 记录。

        Args:
            conversation_id: 目标 Conversation ID。

        Returns:
            运行记录列表，按创建时间降序排列。
        """
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
        """初始化 Trace 仓储。

        Args:
            db_path: SQLite 数据库文件路径。
        """
        self.db_path = db_path

    async def save(
        self,
        trace_id: str,
        run_id: str,
        iteration: int,
        trace_type: str,
        data: dict[str, Any],
    ) -> str:
        """保存一条执行轨迹。

        Args:
            trace_id: 轨迹 ID。
            run_id: 所属运行记录 ID。
            iteration: 所属迭代序号。
            trace_type: 轨迹类型（如 "thought"、"action"、"observation"、"answer"）。
            data: 轨迹数据（JSON 可序列化字典）。

        Returns:
            保存的轨迹 ID。
        """
        now = _now()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO execution_traces (id, run_id, iteration, trace_type, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (trace_id, run_id, iteration, trace_type, json.dumps(data, ensure_ascii=False), now),
            )
        return trace_id

    async def list_by_run(self, run_id: str) -> list[dict[str, Any]]:
        """获取某个运行记录的所有执行轨迹。

        Args:
            run_id: 运行记录 ID。

        Returns:
            轨迹列表，按创建时间升序排列。
        """
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

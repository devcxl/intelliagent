from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class AgentTeamDB:
    """纯标准库 sqlite3，同步 API。调用方负责线程安全。"""

    def __init__(self, db_path: str) -> None:
        """
        打开连接，启用 WAL 模式 + 外键约束。

        Args:
            db_path: SQLite 数据库文件路径。如果目录不存在则自动创建。
        """
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def init_db(self) -> None:
        """建表 + 索引（幂等，IF NOT EXISTS）。"""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                desc        TEXT DEFAULT '',
                prompt      TEXT DEFAULT '',
                status      TEXT DEFAULT 'offline'
                    CHECK(status IN ('online', 'offline', 'busy', 'deleted')),
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_messages (
                id          TEXT PRIMARY KEY,
                sender_id   TEXT NOT NULL,
                receiver_id TEXT NOT NULL,
                content     TEXT NOT NULL,
                is_read     INTEGER DEFAULT 0 CHECK(is_read IN (0, 1)),
                created_at  TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_agent_messages_inbox
                ON agent_messages(receiver_id, is_read, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_agent_messages_sender
                ON agent_messages(sender_id, created_at DESC);
        """)

    # ── Agent CRUD ────────────────────────────────────────────────────────

    def insert_agent(
        self,
        id: str,
        name: str,
        desc: str,
        prompt: str,
        status: str,
        created_at: str,
        updated_at: str,
    ) -> dict:
        """插入新 Agent，返回完整 dict。"""
        self._conn.execute(
            "INSERT INTO agents (id, name, desc, prompt, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (id, name, desc, prompt, status, created_at, updated_at),
        )
        self._conn.commit()
        return self.get_agent(id)

    def get_agent(self, agent_id: str) -> dict | None:
        """按 ID 查询 Agent，不存在返回 None。"""
        row = self._conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        return dict(row) if row else None

    def get_agent_by_name(self, name: str) -> dict | None:
        """按 name 查询 Agent（用于同名检查），不存在返回 None。"""
        row = self._conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def list_agents(
        self,
        exclude_id: str | None = None,
        status_filter: str | None = None,
    ) -> list[dict]:
        """
        列出 Agent，支持：
        - 排除指定 ID（用于通讯录排除当前 Agent）
        - 按 status 过滤（如 'online'、'busy'）
        默认不过滤 status='deleted'（由 Service 层决定是否排除）。
        """
        query = "SELECT * FROM agents WHERE 1=1"
        params: list[str] = []

        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)

        if status_filter is not None:
            query += " AND status = ?"
            params.append(status_filter)

        query += " ORDER BY name ASC"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def delete_agent(self, agent_id: str) -> bool:
        """
        软删除 Agent：将 status 设为 'deleted'，更新 updated_at。
        返回 True 表示更新成功（更新了 1 行），False 表示 Agent 不存在（0 行）。
        """
        now = datetime.now(timezone.utc).isoformat()
        cur = self._conn.execute(
            "UPDATE agents SET status = 'deleted', updated_at = ? WHERE id = ?",
            (now, agent_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    # ── Message CRUD ──────────────────────────────────────────────────────

    def insert_message(
        self,
        id: str,
        sender_id: str,
        receiver_id: str,
        content: str,
        created_at: str,
    ) -> dict:
        """插入新消息，返回完整 dict（不含 sender_name，需后续 JOIN）。"""
        self._conn.execute(
            "INSERT INTO agent_messages (id, sender_id, receiver_id, content, is_read, created_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (id, sender_id, receiver_id, content, created_at),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT id, sender_id, receiver_id, content, is_read, created_at "
            "FROM agent_messages WHERE id = ?", (id,)
        ).fetchone()
        return dict(row)

    def list_messages(
        self,
        receiver_id: str,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> tuple[list[dict], int]:
        """
        查询收件箱消息，返回 (消息列表, 总数)。

        消息列表每项含 sender_name（LEFT JOIN agents），
        按 created_at DESC 排序。
        当 unread_only=True 时只返回 is_read=0 的消息。
        """
        base_query = """
            SELECT m.id, m.sender_id, m.receiver_id, m.content,
                   m.is_read, m.created_at, a.name AS sender_name
            FROM agent_messages m
            LEFT JOIN agents a ON a.id = m.sender_id
            WHERE m.receiver_id = ?
        """
        params: list[str | int] = [receiver_id]

        if unread_only:
            base_query += " AND m.is_read = 0"

        # 先查总数（不带 LIMIT/OFFSET）
        count_query = f"SELECT COUNT(*) FROM ({base_query})"
        total = self._conn.execute(count_query, params).fetchone()[0]

        # 再查分页数据
        data_query = f"{base_query} ORDER BY m.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(data_query, params).fetchall()

        return [dict(row) for row in rows], total

    def mark_as_read(self, message_ids: list[str]) -> None:
        """批量标记已读：UPDATE agent_messages SET is_read = 1 WHERE id IN (...)。"""
        if not message_ids:
            return
        placeholders = ",".join("?" * len(message_ids))
        self._conn.execute(
            f"UPDATE agent_messages SET is_read = 1 WHERE id IN ({placeholders})",
            message_ids,
        )
        self._conn.commit()

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def close(self) -> None:
        """关闭数据库连接。"""
        self._conn.close()

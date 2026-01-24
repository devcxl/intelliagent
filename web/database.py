#!/usr/bin/env python3
"""
SQLite 数据库管理模块
处理会话数据的持久化存储
"""
import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
from utils.logger import logger


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, db_path: str = "intelliagent.db"):
        self.db_path = Path(db_path)
        self._initialized = False

    async def initialize(self):
        """初始化数据库表"""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    task TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'idle',
                    logs TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            await db.commit()
            logger.info(f"数据库初始化完成 | path={self.db_path}")
            self._initialized = True

    async def create_session(
        self,
        session_id: str,
        title: str,
        task: str = "",
        status: str = "idle"
    ) -> Dict[str, Any]:
        """创建新会话"""
        now = datetime.utcnow().isoformat()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO sessions (id, title, task, status, logs, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, title, task, status, "[]", now, now)
            )
            await db.commit()
            logger.info(f"创建会话 | id={session_id}, title={title}")
            
        return {
            "id": session_id,
            "title": title,
            "task": task,
            "status": status,
            "logs": [],
            "createdAt": now,
            "updatedAt": now
        }

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """获取所有会话"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, title, task, status, logs, created_at, updated_at
                FROM sessions
                ORDER BY updated_at DESC
                """
            )
            rows = await cursor.fetchall()
            
            sessions = []
            for row in rows:
                sessions.append({
                    "id": row["id"],
                    "title": row["title"],
                    "task": row["task"],
                    "status": row["status"],
                    "logs": json.loads(row["logs"]),
                    "createdAt": row["created_at"],
                    "updatedAt": row["updated_at"]
                })
            
            logger.debug(f"获取会话列表 | count={len(sessions)}")
            return sessions

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取指定会话"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT id, title, task, status, logs, created_at, updated_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                return None
            
            return {
                "id": row["id"],
                "title": row["title"],
                "task": row["task"],
                "status": row["status"],
                "logs": json.loads(row["logs"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"]
            }

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        task: Optional[str] = None,
        status: Optional[str] = None,
        logs: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """更新会话"""
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        
        if task is not None:
            updates.append("task = ?")
            params.append(task)
        
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        
        if logs is not None:
            updates.append("logs = ?")
            params.append(json.dumps(logs))
        
        updates.append("updated_at = ?")
        params.append(datetime.utcnow().isoformat())
        
        params.append(session_id)
        
        if not updates:
            return False
        
        async with aiosqlite.connect(self.db_path) as db:
            query = f"UPDATE sessions SET {', '.join(updates)} WHERE id = ?"
            cursor = await db.execute(query, params)
            await db.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"更新会话 | id={session_id}, updates={len(updates)-1}")
                return True
            
            return False

    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM sessions WHERE id = ?",
                (session_id,)
            )
            await db.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"删除会话 | id={session_id}")
                return True
            
            return False

    async def append_log(self, session_id: str, log: Dict[str, Any]) -> bool:
        """向会话添加日志"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        logs = session.get("logs", [])
        logs.append(log)
        
        return await self.update_session(session_id, logs=logs)

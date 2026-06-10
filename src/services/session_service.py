#!/usr/bin/env python3
"""会话服务层。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.web.database import DatabaseManager


class SessionService:
    """对会话相关数据库操作做薄封装。"""

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def create_session(
        self,
        *,
        session_id: str,
        title: str,
        task: str = "",
        status: str = "idle",
    ) -> Dict[str, Any]:
        return await self.db_manager.create_session(
            session_id=session_id,
            title=title,
            task=task,
            status=status,
        )

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.db_manager.get_session(session_id)

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        return await self.db_manager.get_all_sessions()

    async def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        task: str | None = None,
        status: str | None = None,
        logs: List[Dict[str, Any]] | None = None,
    ) -> bool:
        return await self.db_manager.update_session(
            session_id=session_id,
            title=title,
            task=task,
            status=status,
            logs=logs,
        )

    async def delete_session(self, session_id: str) -> bool:
        return await self.db_manager.delete_session(session_id)

    async def append_log(self, session_id: str, log: Dict[str, Any]) -> bool:
        return await self.db_manager.append_log(session_id, log)

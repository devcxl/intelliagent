#!/usr/bin/env python3
"""
SQLite 数据库兼容适配层。

PR3 之后正式数据模型已切换到 users / conversations / runs / messages /
execution_traces。这里保留旧的 DatabaseManager 接口，只用于过渡当前
session API 和已有测试。

@deprecated 请逐步迁移到直接使用 src.db.repositories。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any

from src.db import DatabaseSessionManager
from src.db.models import Conversation
from src.db.repositories import ConversationRepository, UserRepository
from src.utils.logger import logger


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_sqlite_database_path(database_url: str) -> Path:
    """将当前阶段使用的 SQLite DATABASE_URL 转成文件路径。"""
    if not database_url.startswith("sqlite:///"):
        raise ValueError(
            f"当前阶段数据层仅支持 sqlite DATABASE_URL，收到: {database_url}"
        )

    raw_path = database_url[len("sqlite:///"):]
    if not raw_path:
        return Path.cwd() / "intelliagent.db"

    if database_url.startswith("sqlite:////"):
        return Path("/" + database_url[len("sqlite:////"):])

    path = Path(raw_path)
    if path.is_absolute():
        return path
    return Path.cwd() / path


class DatabaseManager:
    """旧会话接口的兼容适配器。@deprecated"""

    def __init__(self, db_path: str = "intelliagent.db"):
        self.db_path = Path(db_path)
        self.database_url = f"sqlite:///{self.db_path}"
        self.session_manager = DatabaseSessionManager(self.database_url)
        self.user_repository = UserRepository(self.session_manager)
        self.conversation_repository = ConversationRepository(self.session_manager)
        self._initialized = False

    async def initialize(self):
        """初始化数据库表并种下默认匿名用户。"""
        if self._initialized:
            return

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        await self.session_manager.create_all()
        await self.user_repository.get_or_create_local_user()
        logger.info(f"数据库初始化完成 | path={self.db_path}")
        self._initialized = True

    @staticmethod
    def _serialize_session(conversation: Conversation) -> Dict[str, Any]:
        return {
            "id": conversation.id,
            "title": conversation.title,
            "task": conversation.task,
            "status": conversation.status,
            "logs": [],
            "createdAt": conversation.created_at.isoformat(),
            "updatedAt": conversation.updated_at.isoformat(),
        }

    async def create_session(
        self,
        session_id: str,
        title: str,
        task: str = "",
        status: str = "idle"
    ) -> Dict[str, Any]:
        """创建新会话。"""
        conversation = await self.conversation_repository.create(
            conversation_id=session_id,
            user_id="local",
            title=title,
            task=task,
            status=status,
        )
        logger.info(f"创建会话 | id={session_id}, title={title}")
        return self._serialize_session(conversation)

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """获取所有会话。"""
        conversations = await self.conversation_repository.list_all()
        sessions = [self._serialize_session(conversation) for conversation in conversations]
        logger.debug(f"获取会话列表 | count={len(sessions)}")
        return sessions

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取指定会话。"""
        conversation = await self.conversation_repository.get(session_id)
        if conversation is None:
            return None
        return self._serialize_session(conversation)

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        task: Optional[str] = None,
        status: Optional[str] = None,
        logs: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """更新会话。

        PR3 已不再把 logs 当正式数据模型的一部分。若调用方仍传 logs，当前仅忽略。
        """
        if logs is not None:
            logger.warning("更新会话时收到 logs，但 PR3 已不再持久化 logs 字段")

        conversation = await self.conversation_repository.update(
            session_id,
            title=title,
            task=task,
            status=status,
        )
        if conversation is None:
            return False

        logger.info(f"更新会话 | id={session_id}")
        return True

    async def delete_session(self, session_id: str) -> bool:
        """删除会话。"""
        success = await self.conversation_repository.delete(session_id)
        if success:
            logger.info(f"删除会话 | id={session_id}")
        return success

    async def append_log(self, session_id: str, log: Dict[str, Any]) -> bool:
        """兼容旧接口；PR3 之后不再持久化 logs。"""
        if await self.get_session(session_id) is None:
            return False

        logger.warning("append_log 已弃用：PR3 后 logs 不再持久化")
        return True

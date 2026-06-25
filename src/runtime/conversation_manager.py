"""ConversationManager — 管理会话生命周期与消息持久化。"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.db.engine import create_engine as create_db_engine
from src.db.engine import create_session_factory, init_db
from src.db.models import Conversation, Message
from src.db.repositories import ConversationRepository, MessageRepository
from src.db.repositories._utils import new_uuid
from src.tools.agent_team_tools import set_agent_team_context
from src.tools.task_tools import set_task_context


class ConversationManager:
    """封装 Conversation CRUD、历史加载和工具上下文注入。

    Runtime 只负责组装依赖；会话生命周期和 DB 会话管理集中放在这里，避免
    AgentRuntime 同时承担组合根和业务编排两种职责。
    """

    def __init__(self, database_url: str, agent_id: str = "agent-001") -> None:
        self._database_url = database_url
        self._agent_id = agent_id
        self._db_engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._conversation_id: str | None = None
        self._is_new = True
        self._warnings: list[str] = []

    @property
    def conversation_id(self) -> str | None:
        return self._conversation_id

    @property
    def is_new(self) -> bool:
        return self._is_new

    @property
    def warnings(self) -> list[str]:
        return self._warnings

    async def initialize(self) -> None:
        await init_db(self._get_db_engine())

    async def shutdown(self) -> None:
        if self._db_engine is not None:
            # 测试和长时间运行的 CLI 都需要显式释放 aiosqlite 后台线程。
            await self._db_engine.dispose()
            self._db_engine = None
            self._session_factory = None

    def _get_db_engine(self) -> AsyncEngine:
        if self._db_engine is None:
            self._db_engine = create_db_engine(self._database_url)
        return self._db_engine

    def _get_session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            self._session_factory = create_session_factory(self._get_db_engine())
        return self._session_factory

    async def setup_conversation(
        self,
        task: str,
        session_id: str | None = None,
        resume: bool = False,
    ) -> str:
        self._warnings = []

        session_factory = self._get_session_factory()
        async with session_factory() as session:
            conversation_id = await self._resolve_conversation(session, task, session_id, resume)

        self._conversation_id = conversation_id
        # 工具函数没有持有 Runtime 实例，只能通过上下文拿到当前会话和 Agent 身份。
        set_task_context(session_factory, conversation_id)
        set_agent_team_context(session_factory, self._agent_id)
        return conversation_id

    async def _resolve_conversation(
        self,
        session: AsyncSession,
        task: str,
        session_id: str | None,
        resume: bool,
    ) -> str:
        conv_repo = ConversationRepository(session)

        if session_id:
            return await self._setup_by_id(conv_repo, session_id, task)
        if resume:
            return await self._setup_latest(conv_repo, task)
        return await self._create_conversation(conv_repo, task)

    async def _setup_by_id(self, conv_repo: ConversationRepository, session_id: str, task: str) -> str:
        existing = await conv_repo.get(session_id)
        if existing is None:
            # 明确 session_id 时保留调用方给出的 ID，便于外部恢复同一个会话别名。
            self._warnings.append(f"Conversation {session_id} 不存在，将创建新 Conversation。")
            await conv_repo.save(Conversation(id=session_id, title=task[:80]))
            self._is_new = True
            return session_id

        await conv_repo.update(session_id, status="running")
        self._is_new = False
        return session_id

    async def _setup_latest(self, conv_repo: ConversationRepository, task: str) -> str:
        latest = await conv_repo.get_latest()
        if latest:
            conversation_id = latest["id"]
            await conv_repo.update(conversation_id, status="running")
            self._is_new = False
            return conversation_id

        self._warnings.append("没有历史 Conversation，将创建新 Conversation。")
        return await self._create_conversation(conv_repo, task)

    async def _create_conversation(self, conv_repo: ConversationRepository, task: str) -> str:
        conversation_id = f"conv-{uuid.uuid4()}"
        await conv_repo.save(Conversation(id=conversation_id, title=task[:80]))
        self._is_new = True
        return conversation_id

    async def save_message(self, role: str, content: str) -> None:
        if self._conversation_id is None:
            return
        async with self._get_session_factory()() as session:
            msg_repo = MessageRepository(session)
            await msg_repo.save(
                Message(id=new_uuid(), conversation_id=self._conversation_id, role=role, content=content)
            )

    async def load_history_messages(self) -> list[dict[str, Any]]:
        if self._conversation_id is None:
            return []
        async with self._get_session_factory()() as session:
            msg_repo = MessageRepository(session)
            messages = await msg_repo.list_by_conversation(self._conversation_id)
        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    async def list_conversations(self) -> list[dict[str, Any]]:
        async with self._get_session_factory()() as session:
            conv_repo = ConversationRepository(session)
            return await conv_repo.list_all()

    async def get_message_count(self, conversation_id: str) -> int:
        async with self._get_session_factory()() as session:
            msg_repo = MessageRepository(session)
            return len(await msg_repo.list_by_conversation(conversation_id))


__all__ = ["ConversationManager"]

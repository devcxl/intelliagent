"""Conversation / Message / Task Repository 单元测试。

覆盖 BaseRepository.save/get + 各子类的自定义查询方法。
使用 in-memory SQLite，与 test_agent_team_db.py 保持一致的测试模式。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, Conversation, Message, Task
from src.db.repositories.conversation import ConversationRepository
from src.db.repositories.message import MessageRepository
from src.db.repositories.task import TaskRepository


@pytest.fixture
async def session():
    """创建内存 SQLite 数据库和 session。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def conv_repo(session: AsyncSession) -> ConversationRepository:
    return ConversationRepository(session)


@pytest.fixture
def msg_repo(session: AsyncSession) -> MessageRepository:
    return MessageRepository(session)


@pytest.fixture
def task_repo(session: AsyncSession) -> TaskRepository:
    return TaskRepository(session)


def _conv(id: str, title: str = "测试对话", updated_at: datetime | None = None) -> Conversation:
    now = updated_at or datetime.now(timezone.utc)
    return Conversation(id=id, title=title, status="idle", created_at=now, updated_at=now)


def _msg(id: str, conv_id: str, role: str = "user", content: str = "hello") -> Message:
    return Message(id=id, conversation_id=conv_id, role=role, content=content, created_at=datetime.now(timezone.utc))


def _task(id: str, conv_id: str, title: str = "任务", sort_order: int = 0) -> Task:
    return Task(id=id, conversation_id=conv_id, title=title, status="pending", priority="medium", sort_order=sort_order)


# ============================================================================
# ConversationRepository
# ============================================================================


class TestConversationRepository:
    async def test_save_and_get(self, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1", "对话1"))

        fetched = await conv_repo.get("c1")
        assert fetched is not None
        assert fetched.title == "对话1"
        assert fetched.status == "idle"

    async def test_update_title(self, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1", "旧标题"))

        result = await conv_repo.update("c1", title="新标题")
        assert result is True

        fetched = await conv_repo.get("c1")
        assert fetched.title == "新标题"

    async def test_update_status(self, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))

        await conv_repo.update("c1", status="active")
        fetched = await conv_repo.get("c1")
        assert fetched.status == "active"

    async def test_update_nonexistent_returns_false(self, conv_repo: ConversationRepository):
        result = await conv_repo.update("nonexistent", title="x")
        assert result is False

    async def test_delete(self, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))

        result = await conv_repo.delete("c1")
        assert result is True

        assert await conv_repo.get("c1") is None

    async def test_list_all(self, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1", "对话1"))
        await conv_repo.save(_conv("c2", "对话2"))

        result = await conv_repo.list_all()
        assert len(result) == 2

    async def test_list_all_ordered_by_updated_at_desc(self, conv_repo: ConversationRepository):
        base = datetime.now(timezone.utc)
        await conv_repo.save(_conv("c1", "第一", updated_at=base))
        await conv_repo.save(_conv("c2", "第二", updated_at=base + timedelta(seconds=1)))

        result = await conv_repo.list_all()
        assert len(result) == 2
        assert result[0].id == "c2"

    async def test_get_latest(self, conv_repo: ConversationRepository):
        base = datetime.now(timezone.utc)
        await conv_repo.save(_conv("c1", "第一", updated_at=base))
        await conv_repo.save(_conv("c2", "第二", updated_at=base + timedelta(seconds=1)))

        latest = await conv_repo.get_latest()
        assert latest is not None
        assert latest.id == "c2"

    async def test_get_latest_empty(self, conv_repo: ConversationRepository):
        assert await conv_repo.get_latest() is None


# ============================================================================
# MessageRepository
# ============================================================================


class TestMessageRepository:
    async def test_save_and_get(self, msg_repo: MessageRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))

        msg = await msg_repo.save(_msg("m1", "c1", "user", "你好"))
        assert msg.id == "m1"

        fetched = await msg_repo.get("m1")
        assert fetched is not None
        assert fetched.content == "你好"
        assert fetched.role == "user"

    async def test_list_by_conversation(self, msg_repo: MessageRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))

        await msg_repo.save(_msg("m1", "c1", "user", "问题"))
        await msg_repo.save(_msg("m2", "c1", "assistant", "回答"))

        messages = await msg_repo.list_by_conversation("c1")
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"

    async def test_list_by_conversation_empty(self, msg_repo: MessageRepository):
        messages = await msg_repo.list_by_conversation("nonexistent")
        assert len(messages) == 0

    async def test_list_only_returns_conversation_messages(
        self, msg_repo: MessageRepository, conv_repo: ConversationRepository
    ):
        await conv_repo.save(_conv("c1"))
        await conv_repo.save(_conv("c2"))

        await msg_repo.save(_msg("m1", "c1", "user", "对话1消息"))
        await msg_repo.save(_msg("m2", "c2", "user", "对话2消息"))

        messages = await msg_repo.list_by_conversation("c1")
        assert len(messages) == 1
        assert messages[0].content == "对话1消息"

    async def test_delete_by_ids(self, msg_repo: MessageRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))
        await msg_repo.save(_msg("m1", "c1"))
        await msg_repo.save(_msg("m2", "c1"))
        await msg_repo.save(_msg("m3", "c1"))

        await msg_repo.delete_by_ids("c1", ["m1", "m2"])

        messages = await msg_repo.list_by_conversation("c1")
        assert len(messages) == 1
        assert messages[0].id == "m3"


# ============================================================================
# TaskRepository
# ============================================================================


class TestTaskRepository:
    async def test_save_and_get(self, task_repo: TaskRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))

        task = await task_repo.save(_task("t1", "c1", "任务1"))
        assert task.id == "t1"

        fetched = await task_repo.get("t1")
        assert fetched is not None
        assert fetched.title == "任务1"
        assert fetched.status == "pending"

    async def test_list_by_conversation(self, task_repo: TaskRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))

        await task_repo.save(_task("t1", "c1", "任务1", sort_order=1))
        await task_repo.save(_task("t2", "c1", "任务2", sort_order=0))

        tasks = await task_repo.list_by_conversation("c1")
        assert len(tasks) == 2
        assert tasks[0].id == "t2"
        assert tasks[1].id == "t1"

    async def test_list_by_conversation_empty(self, task_repo: TaskRepository):
        tasks = await task_repo.list_by_conversation("nonexistent")
        assert len(tasks) == 0

    async def test_update_title(self, task_repo: TaskRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))
        await task_repo.save(_task("t1", "c1", "旧标题"))

        result = await task_repo.update("t1", title="新标题")
        assert result is True

        fetched = await task_repo.get("t1")
        assert fetched.title == "新标题"

    async def test_update_status_completed_sets_completed_at(
        self, task_repo: TaskRepository, conv_repo: ConversationRepository
    ):
        await conv_repo.save(_conv("c1"))
        await task_repo.save(_task("t1", "c1"))

        await task_repo.update("t1", status="completed")
        fetched = await task_repo.get("t1")
        assert fetched.status == "completed"
        assert fetched.completed_at is not None

    async def test_update_priority(self, task_repo: TaskRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))
        await task_repo.save(_task("t1", "c1"))

        await task_repo.update("t1", priority="high")
        fetched = await task_repo.get("t1")
        assert fetched.priority == "high"

    async def test_update_nonexistent_returns_false(self, task_repo: TaskRepository):
        result = await task_repo.update("nonexistent", title="x")
        assert result is False

    async def test_delete_by_conversation(self, task_repo: TaskRepository, conv_repo: ConversationRepository):
        await conv_repo.save(_conv("c1"))
        await task_repo.save(_task("t1", "c1"))
        await task_repo.save(_task("t2", "c1"))

        await task_repo.delete_by_conversation("c1")

        tasks = await task_repo.list_by_conversation("c1")
        assert len(tasks) == 0

    async def test_delete_by_conversation_only_deletes_target(
        self, task_repo: TaskRepository, conv_repo: ConversationRepository
    ):
        await conv_repo.save(_conv("c1"))
        await conv_repo.save(_conv("c2"))
        await task_repo.save(_task("t1", "c1"))
        await task_repo.save(_task("t2", "c2"))

        await task_repo.delete_by_conversation("c1")

        assert len(await task_repo.list_by_conversation("c1")) == 0
        assert len(await task_repo.list_by_conversation("c2")) == 1

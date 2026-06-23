"""数据库 ORM 模型与仓储测试。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.engine import create_engine, create_session_factory, init_db
from src.db.models import Conversation, Message, Task
from src.db.repositories import ConversationRepository, MessageRepository, TaskRepository


@pytest.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(str(db_path))
    await init_db(engine)
    factory = create_session_factory(engine)
    yield factory
    await engine.dispose()


@pytest.fixture
async def session(session_factory):
    async with session_factory() as s:
        yield s


class TestSchema:
    async def test_creates_all_tables(self, session_factory):
        async with session_factory() as session:
            # 简单插入验证表存在
            conv = Conversation(id="conv-1", title="test", task="test")
            session.add(conv)
            await session.commit()

            msg = Message(id="msg-1", conversation_id="conv-1", role="user", content="hello")
            session.add(msg)
            await session.commit()

            task = Task(id="task-1", conversation_id="conv-1", title="do something")
            session.add(task)
            await session.commit()

    async def test_cascade_delete_messages_and_tasks(self, session_factory):
        async with session_factory() as session:
            conv = Conversation(id="conv-1", title="test", task="test")
            session.add(conv)
            await session.commit()

            session.add(Message(id="msg-1", conversation_id="conv-1", role="user", content="hello"))
            session.add(Task(id="task-1", conversation_id="conv-1", title="work"))
            await session.commit()

            await session.delete(conv)
            await session.commit()

            msgs = await MessageRepository(session).list_by_conversation("conv-1")
            tasks = await TaskRepository(session).list_by_conversation("conv-1")
            assert msgs == []
            assert tasks == []


class TestConversationRepository:
    @pytest.fixture
    def repo(self, session):
        return ConversationRepository(session)

    async def test_create_and_get(self, repo, session):
        result = await repo.create("conv-1", title="测试", task="任务", status="idle")
        assert result["id"] == "conv-1"

        fetched = await repo.get("conv-1")
        assert fetched is not None
        assert fetched["title"] == "测试"
        assert fetched["status"] == "idle"

    async def test_get_not_found(self, repo):
        assert await repo.get("nonexistent") is None

    async def test_update(self, repo, session):
        await repo.create("conv-1", title="旧", task="t")
        await repo.update("conv-1", title="新", status="running")

        fetched = await repo.get("conv-1")
        assert fetched["title"] == "新"
        assert fetched["status"] == "running"

    async def test_delete_cascades(self, repo, session):
        await repo.create("conv-1", title="test", task="t")
        msg_repo = MessageRepository(session)
        task_repo = TaskRepository(session)
        await msg_repo.save("conv-1", "user", "hello")
        await task_repo.add("conv-1", title="task")

        await repo.delete("conv-1")

        assert await repo.get("conv-1") is None
        assert await msg_repo.list_by_conversation("conv-1") == []
        assert await task_repo.list_by_conversation("conv-1") == []

    async def test_list_all_ordered_by_updated_at(self, repo):
        await repo.create("conv-1", title="first")
        await repo.update("conv-1", status="running")
        await repo.create("conv-2", title="second")

        result = await repo.list_all()
        assert len(result) == 2
        # conv-2 was created after conv-1's update, so conv-2 should be first
        assert result[0]["id"] == "conv-2"

    async def test_get_latest(self, repo):
        await repo.create("conv-1", title="first")
        await repo.create("conv-2", title="second")

        latest = await repo.get_latest()
        assert latest is not None
        assert latest["id"] == "conv-2"


class TestMessageRepository:
    @pytest.fixture
    def repo(self, session):
        return MessageRepository(session)

    async def test_save_and_list(self, repo, session):
        # 需要先创建 conversation（FK 约束）
        conv_repo = ConversationRepository(session)
        await conv_repo.create("conv-1")

        msg_id = await repo.save("conv-1", "user", "hello")
        assert msg_id.startswith("msg-")

        msgs = await repo.list_by_conversation("conv-1")
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "hello"


class TestTaskRepository:
    @pytest.fixture
    def repo(self, session):
        return TaskRepository(session)

    @pytest.fixture
    async def conv(self, session):
        conv_repo = ConversationRepository(session)
        await conv_repo.create("conv-1")
        return "conv-1"

    async def test_add_and_get(self, repo, conv):
        result = await repo.add(conv, title="设计API", content="设计REST", priority="high")
        assert result["id"].startswith("task-")
        assert result["status"] == "pending"

        task = await repo.get(result["id"])
        assert task is not None
        assert task["title"] == "设计API"
        assert task["priority"] == "high"
        assert task["status"] == "pending"
        assert task["completed_at"] is None

    async def test_add_with_parent(self, repo, conv):
        parent = await repo.add(conv, title="父任务")
        child = await repo.add(conv, title="子任务", parent_id=parent["id"])

        task = await repo.get(child["id"])
        assert task["parent_id"] == parent["id"]

    async def test_list_by_conversation(self, repo, conv):
        await repo.add(conv, title="任务1", sort_order=0)
        await repo.add(conv, title="任务2", sort_order=1)
        await repo.add(conv, title="任务3", sort_order=2)

        tasks = await repo.list_by_conversation(conv)
        assert len(tasks) == 3
        assert tasks[0]["title"] == "任务1"

    async def test_update_status_completed(self, repo, conv):
        result = await repo.add(conv, title="待完成")
        await repo.update(result["id"], status="completed")

        task = await repo.get(result["id"])
        assert task["status"] == "completed"
        assert task["completed_at"] is not None

    async def test_update_multiple_fields(self, repo, conv):
        result = await repo.add(conv, title="原始", content="内容", priority="low")
        await repo.update(result["id"], title="新标题", priority="high")

        task = await repo.get(result["id"])
        assert task["title"] == "新标题"
        assert task["priority"] == "high"
        assert task["content"] == "内容"

    async def test_delete_by_conversation(self, repo, conv):
        await repo.add(conv, title="A")
        await repo.add(conv, title="B")
        assert len(await repo.list_by_conversation(conv)) == 2

        await repo.delete_by_conversation(conv)
        assert len(await repo.list_by_conversation(conv)) == 0

    async def test_isolated_conversations(self, repo, session):
        conv_repo = ConversationRepository(session)
        await conv_repo.create("conv-1")
        await conv_repo.create("conv-2")
        await repo.add("conv-1", title="conv1任务")
        await repo.add("conv-2", title="conv2任务")
        assert len(await repo.list_by_conversation("conv-1")) == 1
        assert len(await repo.list_by_conversation("conv-2")) == 1

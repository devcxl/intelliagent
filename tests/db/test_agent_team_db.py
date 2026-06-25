"""Agent Repository 单元测试 — 基于 SQLAlchemy ORM。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Agent, Base, Relay
from src.db.repositories import AgentRepository, RelayRepository


@pytest.fixture
async def session():
    """创建内存 SQLite 数据库和 session。"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    # 显式释放 engine，避免 aiosqlite 后台线程在事件循环关闭后继续回调。
    await engine.dispose()


@pytest.fixture
def agent_repo(session: AsyncSession) -> AgentRepository:
    return AgentRepository(session)


@pytest.fixture
def msg_repo(session: AsyncSession) -> RelayRepository:
    return RelayRepository(session)


def _agent(id: str, name: str, status: str = "online") -> Agent:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return Agent(id=id, name=name, desc="", prompt="", status=status, created_at=now, updated_at=now)


def _relay(id: str, sender_id: str = "s", receiver_id: str = "r", content: str = "msg", created_at=None) -> Relay:
    from datetime import datetime, timezone

    return Relay(
        id=id,
        sender_id=sender_id,
        receiver_id=receiver_id,
        content=content,
        is_read=False,
        created_at=created_at or datetime.now(timezone.utc),
    )


@pytest.fixture
async def sample_agent(agent_repo: AgentRepository) -> Agent:
    return await agent_repo.save(
        Agent(
            id="agent-001",
            name="CodeReviewer",
            desc="代码审查 Agent",
            prompt="你是代码审查专家",
            status="online",
        )
    )


class TestAgentRepository:
    async def test_insert_and_get(self, agent_repo: AgentRepository, sample_agent: Agent) -> None:
        fetched = await agent_repo.get(sample_agent.id)
        assert fetched is not None
        assert fetched.name == "CodeReviewer"
        assert fetched.status == "online"

    async def test_get_by_name_found(self, agent_repo: AgentRepository, sample_agent: Agent) -> None:
        fetched = await agent_repo.get_by_name("CodeReviewer")
        assert fetched is not None
        assert fetched.id == sample_agent.id

    async def test_get_by_name_not_found(self, agent_repo: AgentRepository) -> None:
        assert await agent_repo.get_by_name("nonexistent") is None

    async def test_list_all(self, agent_repo: AgentRepository, session: AsyncSession) -> None:
        await agent_repo.save(_agent("a1", "Alpha", "online"))
        await agent_repo.save(_agent("a2", "Beta", "offline"))
        result = await agent_repo.list()
        assert len(result) == 2
        assert [r.name for r in result] == ["Alpha", "Beta"]

    async def test_list_exclude_id(self, agent_repo: AgentRepository) -> None:
        await agent_repo.save(_agent("a1", "Alpha", "online"))
        await agent_repo.save(_agent("a2", "Beta", "offline"))
        result = await agent_repo.list(exclude_id="a1")
        assert len(result) == 1
        assert result[0].id == "a2"

    async def test_list_status_filter(self, agent_repo: AgentRepository) -> None:
        await agent_repo.save(_agent("a1", "Alpha", "online"))
        await agent_repo.save(_agent("a2", "Beta", "offline"))
        result = await agent_repo.list(status_filter="online")
        assert len(result) == 1
        assert result[0].id == "a1"

    async def test_delete_soft(self, agent_repo: AgentRepository, sample_agent: Agent) -> None:
        result = await agent_repo.delete(sample_agent.id)
        assert result is True
        fetched = await agent_repo.get(sample_agent.id)
        assert fetched is not None
        assert fetched.status == "deleted"

    async def test_delete_not_found(self, agent_repo: AgentRepository) -> None:
        result = await agent_repo.delete("nonexistent")
        assert result is False


class TestRelayRepository:
    async def test_insert_and_list(self, msg_repo: RelayRepository, session: AsyncSession) -> None:
        msg = await msg_repo.save(_relay("msg-1", "sender-1", "receiver-1", "Hello"))
        assert msg.id == "msg-1"
        assert msg.is_read == 0

        messages, total = await msg_repo.list_by_receiver("receiver-1", limit=10, offset=0)
        assert total == 1
        assert len(messages) == 1
        assert messages[0].relay.id == "msg-1"

    async def test_list_with_sender_name(self, msg_repo: RelayRepository, agent_repo: AgentRepository) -> None:
        await agent_repo.save(_agent("sender-1", "SenderName"))
        await msg_repo.save(_relay("msg-1", "sender-1", "receiver-1", "Hello"))
        messages, total = await msg_repo.list_by_receiver("receiver-1", limit=10, offset=0)
        assert total == 1
        assert messages[0].sender_name == "SenderName"

    async def test_list_unread_only(self, msg_repo: RelayRepository) -> None:
        await msg_repo.save(_relay("m1", content="a"))
        await msg_repo.save(_relay("m2", content="b"))
        await msg_repo.mark_as_read(["m1"])
        messages, total = await msg_repo.list_by_receiver("r", limit=10, offset=0, unread_only=True)
        assert total == 1
        assert messages[0].relay.id == "m2"

    async def test_list_pagination(self, msg_repo: RelayRepository) -> None:
        from datetime import datetime, timezone

        for i in range(5):
            await msg_repo.save(_relay(f"m{i}", content=f"msg-{i}", created_at=datetime.now(timezone.utc)))
        page1, total = await msg_repo.list_by_receiver("r", limit=2, offset=0)
        assert total == 5
        assert len(page1) == 2
        page2, total = await msg_repo.list_by_receiver("r", limit=2, offset=2)
        assert total == 5
        assert len(page2) == 2

    async def test_mark_as_read(self, msg_repo: RelayRepository) -> None:
        await msg_repo.save(_relay("m1", content="a"))
        await msg_repo.save(_relay("m2", content="b"))
        await msg_repo.mark_as_read(["m1", "m2"])
        messages, _ = await msg_repo.list_by_receiver("r", limit=10, offset=0)
        assert all(m.relay.is_read == 1 for m in messages)

    async def test_mark_as_read_empty(self, msg_repo: RelayRepository) -> None:
        await msg_repo.mark_as_read([])

    async def test_list_sort_order(self, msg_repo: RelayRepository) -> None:
        from datetime import datetime, timedelta, timezone

        base = datetime.now(timezone.utc)
        await msg_repo.save(_relay("m1", content="first", created_at=base))
        await msg_repo.save(_relay("m2", content="second", created_at=base + timedelta(seconds=1)))
        await msg_repo.save(_relay("m3", content="third", created_at=base + timedelta(seconds=2)))
        messages, total = await msg_repo.list_by_receiver("r", limit=10, offset=0)
        assert total == 3
        assert [m.relay.id for m in messages] == ["m3", "m2", "m1"]

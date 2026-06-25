"""Agent Team Tool 层单元测试 — 基于 SQLAlchemy ORM。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Agent, Base, Relay
from src.db.repositories import AgentRepository, RelayRepository
from src.tools.agent_team_tools import AgentTeamTools

_RECEIVER_ID = "11111111-1111-1111-1111-111111111111"
_TESTER_ID = "agent-tester-001"


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def initialized_factory(factory: async_sessionmaker[AsyncSession]) -> async_sessionmaker[AsyncSession]:
    now = datetime.now(timezone.utc)
    async with factory() as session:
        repo = AgentRepository(session)
        await repo.save(Agent(id=_TESTER_ID, name="Tester", desc="测试者", prompt="", status="online", created_at=now))
        await repo.save(
            Agent(id=_RECEIVER_ID, name="Receiver", desc="接收方", prompt="", status="online", created_at=now)
        )
    return factory


@pytest.fixture
def tools(initialized_factory: async_sessionmaker[AsyncSession]) -> AgentTeamTools:
    return AgentTeamTools(lambda: initialized_factory, _TESTER_ID)


@pytest.fixture
def empty_tools(factory: async_sessionmaker[AsyncSession]) -> AgentTeamTools:
    return AgentTeamTools(lambda: factory, _TESTER_ID)


async def _insert_message(factory: async_sessionmaker[AsyncSession], content: str, idx: int = 0) -> str:
    message_id = f"test-msg-{idx}"
    async with factory() as session:
        repo = RelayRepository(session)
        await repo.save(
            Relay(
                id=message_id,
                sender_id=_RECEIVER_ID,
                receiver_id=_TESTER_ID,
                content=content,
                is_read=False,
                created_at=datetime.now(timezone.utc),
            )
        )
    return message_id


class TestSendMessageTool:
    @pytest.mark.asyncio
    async def test_send_success(self, tools: AgentTeamTools, initialized_factory: async_sessionmaker[AsyncSession]):
        result = await tools.send_message(to_agent_id=_RECEIVER_ID, content="hello team")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "message_id" in data

        async with initialized_factory() as session:
            repo = RelayRepository(session)
            messages, total = await repo.list_by_receiver(_RECEIVER_ID, 10, 0)
            assert total == 1
            assert messages[0].relay.content == "hello team"
            assert messages[0].relay.sender_id == _TESTER_ID

    @pytest.mark.asyncio
    async def test_send_empty_content(self, tools: AgentTeamTools):
        data = json.loads(await tools.send_message(to_agent_id=_RECEIVER_ID, content=""))
        assert data["status"] == "error" and data["code"] == "EMPTY_CONTENT"

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_agent(self, tools: AgentTeamTools):
        data = json.loads(await tools.send_message(to_agent_id="nonexistent", content="hello"))
        assert data["status"] == "error" and data["code"] == "AGENT_NOT_FOUND"


class TestReceiveMessageTool:
    @pytest.mark.asyncio
    async def test_receive_empty_inbox(self, tools: AgentTeamTools):
        data = json.loads(await tools.receive_message())
        assert data["status"] == "ok"
        assert data["messages"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_receive_pagination(
        self, tools: AgentTeamTools, initialized_factory: async_sessionmaker[AsyncSession]
    ):
        for i in range(5):
            await _insert_message(initialized_factory, f"content-{i}", i)

        page1 = json.loads(await tools.receive_message(limit=2, offset=0))
        page2 = json.loads(await tools.receive_message(limit=2, offset=2))

        assert page1["status"] == "ok"
        assert len(page1["messages"]) == 2
        assert page1["total"] == 5
        assert len(page2["messages"]) == 2

    @pytest.mark.asyncio
    async def test_receive_mark_as_read(
        self, tools: AgentTeamTools, initialized_factory: async_sessionmaker[AsyncSession]
    ):
        await _insert_message(initialized_factory, "mark-read-test")
        await tools.receive_message()

        async with initialized_factory() as session:
            repo = RelayRepository(session)
            messages, _ = await repo.list_by_receiver(_TESTER_ID, 10, 0)
            assert messages[0].relay.is_read == 1

    @pytest.mark.asyncio
    async def test_receive_unread_only(
        self, tools: AgentTeamTools, initialized_factory: async_sessionmaker[AsyncSession]
    ):
        await _insert_message(initialized_factory, "已读", 0)
        await _insert_message(initialized_factory, "未读", 1)
        await tools.receive_message()
        await _insert_message(initialized_factory, "新未读", 2)

        result = json.loads(await tools.receive_message(unread_only=True))
        assert result["status"] == "ok"
        assert result["total"] == 1
        assert result["messages"][0]["content"] == "新未读"


class TestContactsTool:
    @pytest.mark.asyncio
    async def test_get_contacts_excludes_current(self, tools: AgentTeamTools):
        data = json.loads(await tools.get_contacts())
        assert data["status"] == "ok"
        ids = {contact["id"] for contact in data["contacts"]}
        assert _TESTER_ID not in ids
        assert _RECEIVER_ID in ids

    @pytest.mark.asyncio
    async def test_get_contacts_invalid_status(self, tools: AgentTeamTools):
        data = json.loads(await tools.get_contacts(status="invalid"))
        assert data["status"] == "error" and data["code"] == "INVALID_STATUS"

    @pytest.mark.asyncio
    async def test_get_detail_success(self, tools: AgentTeamTools):
        data = json.loads(await tools.get_contact_detail(agent_id=_RECEIVER_ID))
        assert data["status"] == "ok"
        assert data["agent"]["name"] == "Receiver"


class TestCreateAndDeleteAgentTool:
    @pytest.mark.asyncio
    async def test_create_success(self, empty_tools: AgentTeamTools):
        data = json.loads(await empty_tools.create_agent(name="NewAgent", desc="描述", prompt="提示"))
        assert data["status"] == "ok"
        assert data["agent"]["name"] == "NewAgent"
        assert data["agent"]["status"] == "offline"

    @pytest.mark.asyncio
    async def test_create_duplicate_name(self, empty_tools: AgentTeamTools):
        await empty_tools.create_agent(name="UniqueAgent")
        data = json.loads(await empty_tools.create_agent(name="UniqueAgent"))
        assert data["status"] == "error" and data["code"] == "DUPLICATE_NAME"

    @pytest.mark.asyncio
    async def test_delete_success(self, empty_tools: AgentTeamTools):
        created = json.loads(await empty_tools.create_agent(name="ToDelete"))
        data = json.loads(await empty_tools.delete_agent(agent_id=created["agent"]["id"]))
        assert data["status"] == "ok"
        assert data["deleted"] is True


class TestEndToEndFlow:
    @pytest.mark.asyncio
    async def test_send_and_receive_roundtrip(
        self, tools: AgentTeamTools, initialized_factory: async_sessionmaker[AsyncSession]
    ):
        send_resp = json.loads(await tools.send_message(to_agent_id=_RECEIVER_ID, content="roundtrip"))
        assert send_resp["status"] == "ok"

        receiver_tools = AgentTeamTools(lambda: initialized_factory, _RECEIVER_ID)
        recv_resp = json.loads(await receiver_tools.receive_message())
        assert recv_resp["status"] == "ok"
        assert send_resp["message_id"] in [message["id"] for message in recv_resp["messages"]]

        async with initialized_factory() as session:
            repo = RelayRepository(session)
            messages, _ = await repo.list_by_receiver(_RECEIVER_ID, 10, 0)
            assert messages[0].relay.is_read == 1

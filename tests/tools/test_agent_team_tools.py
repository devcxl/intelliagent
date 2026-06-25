"""Agent Team Tool 层单元测试 — 基于 SQLAlchemy ORM。"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Agent, Base, Relay
from src.db.repositories import AgentRepository, RelayRepository
from src.tools.agent_team_tools import (
    create_agent,
    delete_agent,
    get_contact_detail,
    get_contacts,
    receive_message,
    send_message,
    set_agent_team_context,
)

_RECEIVER_ID = "11111111-1111-1111-1111-111111111111"
_TESTER_ID = "agent-tester-001"


@pytest.fixture
async def factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # 显式释放 engine，避免 aiosqlite 后台线程在事件循环关闭后继续回调。
    await engine.dispose()


@pytest.fixture
async def initialized_factory(factory) -> async_sessionmaker[AsyncSession]:
    """预置当前 Agent 和一个接收方 Agent。"""
    now = datetime.now(timezone.utc)
    async with factory() as session:
        repo = AgentRepository(session)
        await repo.save(
            Agent(
                id=_TESTER_ID,
                name="Tester",
                desc="测试者",
                prompt="",
                status="online",
                created_at=now,
                updated_at=now,
            )
        )
        await repo.save(
            Agent(
                id=_RECEIVER_ID,
                name="Receiver",
                desc="接收方",
                prompt="",
                status="online",
                created_at=now,
                updated_at=now,
            )
        )
    return factory


@pytest.fixture
def agent_ctx(factory) -> Generator[async_sessionmaker[AsyncSession], None, None]:
    """未预置数据的上下文。"""
    set_agent_team_context(factory, _TESTER_ID)
    try:
        yield factory
    finally:
        set_agent_team_context(None, None)


@pytest.fixture
def populated_ctx(initialized_factory) -> Generator[async_sessionmaker[AsyncSession], None, None]:
    """已预置接收方 + 上下文已注入。"""
    set_agent_team_context(initialized_factory, _TESTER_ID)
    try:
        yield initialized_factory
    finally:
        set_agent_team_context(None, None)


# ── 上下文缺失 ─────────────────────────────────────────────────────────────


class TestContextNotInitialized:
    @pytest.mark.asyncio
    async def test_send_message_no_context(self):
        data = json.loads(await send_message(to_agent_id="any", content="hello"))
        assert data["status"] == "error" and data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_receive_message_no_context(self):
        data = json.loads(await receive_message())
        assert data["status"] == "error" and data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_get_contacts_no_context(self):
        data = json.loads(await get_contacts())
        assert data["status"] == "error" and data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_get_contact_detail_no_context(self):
        data = json.loads(await get_contact_detail(agent_id="any"))
        assert data["status"] == "error" and data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_create_agent_no_context(self):
        data = json.loads(await create_agent(name="TestAgent"))
        assert data["status"] == "error" and data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_delete_agent_no_context(self):
        data = json.loads(await delete_agent(agent_id="any"))
        assert data["status"] == "error" and data["code"] == "CONTEXT_NOT_INITIALIZED"


# ── send_message ───────────────────────────────────────────────────────────


class TestSendMessageTool:
    @pytest.mark.asyncio
    async def test_send_success(self, populated_ctx):
        result = await send_message(to_agent_id=_RECEIVER_ID, content="hello team")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "message_id" in data
        assert "created_at" in data

        # 验证消息确实存到了 DB
        async with populated_ctx() as session:
            repo = RelayRepository(session)
            msgs, total = await repo.list_by_receiver(_RECEIVER_ID, 10, 0)
            assert total == 1
            assert msgs[0]["content"] == "hello team"
            assert msgs[0]["sender_id"] == _TESTER_ID

    @pytest.mark.asyncio
    async def test_send_empty_content(self, populated_ctx):
        data = json.loads(await send_message(to_agent_id=_RECEIVER_ID, content=""))
        assert data["status"] == "error" and data["code"] == "EMPTY_CONTENT"

    @pytest.mark.asyncio
    async def test_send_whitespace_content(self, populated_ctx):
        data = json.loads(await send_message(to_agent_id=_RECEIVER_ID, content="   \n\t"))
        assert data["status"] == "error" and data["code"] == "EMPTY_CONTENT"

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_agent(self, populated_ctx):
        data = json.loads(await send_message(to_agent_id="nonexistent", content="hello"))
        assert data["status"] == "error" and data["code"] == "AGENT_NOT_FOUND"


# ── receive_message ────────────────────────────────────────────────────────


class TestReceiveMessageTool:
    async def _insert_test_message(self, factory, content: str, idx: int = 0) -> str:
        mid = f"test-msg-{idx}"
        now = datetime.now(timezone.utc)
        async with factory() as session:
            repo = RelayRepository(session)
            await repo.save(
                Relay(
                    id=mid,
                    sender_id=_RECEIVER_ID,
                    receiver_id=_TESTER_ID,
                    content=content,
                    is_read=False,
                    created_at=now,
                )
            )
        return mid

    @pytest.mark.asyncio
    async def test_receive_empty_inbox(self, populated_ctx):
        data = json.loads(await receive_message())
        assert data["status"] == "ok"
        assert data["messages"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_receive_pagination(self, populated_ctx):
        for i in range(5):
            await self._insert_test_message(populated_ctx, f"content-{i}", i)

        page1 = json.loads(await receive_message(limit=2, offset=0))
        assert page1["status"] == "ok"
        assert len(page1["messages"]) == 2
        assert page1["total"] == 5

        page2 = json.loads(await receive_message(limit=2, offset=2))
        assert page2["status"] == "ok"
        assert len(page2["messages"]) == 2
        assert page2["total"] == 5

    @pytest.mark.asyncio
    async def test_receive_mark_as_read(self, populated_ctx):
        await self._insert_test_message(populated_ctx, "mark-read-test", 0)
        await receive_message()

        async with populated_ctx() as session:
            repo = RelayRepository(session)
            msgs, _ = await repo.list_by_receiver(_TESTER_ID, 10, 0)
            assert msgs[0]["is_read"] == 1

    @pytest.mark.asyncio
    async def test_receive_unread_only(self, populated_ctx):
        await self._insert_test_message(populated_ctx, "已读", 0)
        await self._insert_test_message(populated_ctx, "未读", 1)
        await receive_message()
        await self._insert_test_message(populated_ctx, "新未读", 2)

        r = json.loads(await receive_message(unread_only=True))
        assert r["status"] == "ok"
        assert r["total"] == 1
        assert r["messages"][0]["content"] == "新未读"


# ── get_contacts ───────────────────────────────────────────────────────────


class TestGetContactsTool:
    @pytest.mark.asyncio
    async def test_get_contacts_excludes_current(self, populated_ctx):
        data = json.loads(await get_contacts())
        assert data["status"] == "ok"
        ids = {c["id"] for c in data["contacts"]}
        assert _TESTER_ID not in ids

    @pytest.mark.asyncio
    async def test_get_contacts_filter_by_status(self, populated_ctx):
        data = json.loads(await get_contacts(status="online"))
        assert data["status"] == "ok"
        assert all(c["status"] == "online" for c in data["contacts"])

    @pytest.mark.asyncio
    async def test_get_contacts_invalid_status(self, populated_ctx):
        data = json.loads(await get_contacts(status="invalid"))
        assert data["status"] == "error" and data["code"] == "INVALID_STATUS"


# ── get_contact_detail ─────────────────────────────────────────────────────


class TestGetContactDetailTool:
    @pytest.mark.asyncio
    async def test_get_detail_success(self, populated_ctx):
        data = json.loads(await get_contact_detail(agent_id=_RECEIVER_ID))
        assert data["status"] == "ok"
        assert data["agent"]["id"] == _RECEIVER_ID
        assert data["agent"]["name"] == "Receiver"
        assert data["agent"]["status"] == "online"

    @pytest.mark.asyncio
    async def test_get_detail_not_found(self, populated_ctx):
        data = json.loads(await get_contact_detail(agent_id="nonexistent"))
        assert data["status"] == "error" and data["code"] == "AGENT_NOT_FOUND"


# ── create_agent ───────────────────────────────────────────────────────────


class TestCreateAgentTool:
    @pytest.mark.asyncio
    async def test_create_success(self, agent_ctx):
        data = json.loads(await create_agent(name="NewAgent", desc="描述", prompt="提示"))
        assert data["status"] == "ok"
        assert data["agent"]["name"] == "NewAgent"
        assert "id" in data["agent"]
        assert data["agent"]["status"] == "offline"
        assert data["agent"]["allowed_tools"] == ""
        assert data["agent"]["model"] == ""
        assert data["agent"]["workspace"] == ""

    @pytest.mark.asyncio
    async def test_create_with_optional_fields(self, agent_ctx):
        data = json.loads(
            await create_agent(
                name="AdvancedAgent",
                allowed_tools="read,write",
                model="gpt-4",
                workspace="/home/agent",
            )
        )
        assert data["status"] == "ok"
        assert data["agent"]["allowed_tools"] == "read,write"
        assert data["agent"]["model"] == "gpt-4"
        assert data["agent"]["workspace"] == "/home/agent"

    @pytest.mark.asyncio
    async def test_create_duplicate_name(self, agent_ctx):
        await create_agent(name="UniqueAgent")
        data = json.loads(await create_agent(name="UniqueAgent"))
        assert data["status"] == "error" and data["code"] == "DUPLICATE_NAME"

    @pytest.mark.asyncio
    async def test_create_default_values(self, agent_ctx):
        data = json.loads(await create_agent(name="MinimalAgent"))
        assert data["status"] == "ok"
        assert data["agent"]["desc"] == ""
        assert data["agent"]["prompt"] == ""

    @pytest.mark.asyncio
    async def test_create_empty_name(self, agent_ctx):
        data = json.loads(await create_agent(name=""))
        assert data["status"] == "error" and data["code"] == "INVALID_PARAMETERS"

    @pytest.mark.asyncio
    async def test_create_whitespace_name(self, agent_ctx):
        data = json.loads(await create_agent(name="   "))
        assert data["status"] == "error" and data["code"] == "INVALID_PARAMETERS"


# ── delete_agent ───────────────────────────────────────────────────────────


class TestDeleteAgentTool:
    @pytest.mark.asyncio
    async def test_delete_success(self, agent_ctx):
        create_resp = json.loads(await create_agent(name="ToDelete"))
        target_id = create_resp["agent"]["id"]

        data = json.loads(await delete_agent(agent_id=target_id))
        assert data["status"] == "ok"
        assert data["deleted"] is True

        contacts_resp = json.loads(await get_contacts())
        ids = [c["id"] for c in contacts_resp["contacts"]]
        assert target_id not in ids

    @pytest.mark.asyncio
    async def test_delete_not_found(self, agent_ctx):
        data = json.loads(await delete_agent(agent_id="nonexistent"))
        assert data["status"] == "error" and data["code"] == "AGENT_NOT_FOUND"


# ── 端到端 ─────────────────────────────────────────────────────────────────


class TestEndToEndFlow:
    @pytest.mark.asyncio
    async def test_send_and_receive_roundtrip(self, populated_ctx):
        send_resp = json.loads(await send_message(to_agent_id=_RECEIVER_ID, content="roundtrip"))
        assert send_resp["status"] == "ok"
        message_id = send_resp["message_id"]

        set_agent_team_context(populated_ctx, _RECEIVER_ID)
        try:
            recv_resp = json.loads(await receive_message())
            assert recv_resp["status"] == "ok"
            assert recv_resp["total"] >= 1
            ids = [m["id"] for m in recv_resp["messages"]]
            assert message_id in ids
        finally:
            set_agent_team_context(populated_ctx, _TESTER_ID)

        async with populated_ctx() as session:
            repo = RelayRepository(session)
            msgs, _ = await repo.list_by_receiver(_RECEIVER_ID, 10, 0)
            assert msgs[0]["is_read"] == 1

    @pytest.mark.asyncio
    async def test_multi_agent_create_and_chat(self, agent_ctx):
        a = json.loads(await create_agent(name="AgentA", desc="A"))
        assert a["status"] == "ok"

        b = json.loads(await create_agent(name="AgentB", desc="B"))
        assert b["status"] == "ok"
        agent_b_id = b["agent"]["id"]

        send_resp = json.loads(await send_message(to_agent_id=agent_b_id, content="hello from A"))
        assert send_resp["status"] == "ok"

        set_agent_team_context(agent_ctx, agent_b_id)
        try:
            recv_resp = json.loads(await receive_message())
            assert recv_resp["status"] == "ok"
            assert recv_resp["total"] == 1
            assert recv_resp["messages"][0]["content"] == "hello from A"
        finally:
            set_agent_team_context(agent_ctx, _TESTER_ID)

        async with agent_ctx() as session:
            repo = RelayRepository(session)
            msgs, _ = await repo.list_by_receiver(agent_b_id, 10, 0)
            assert msgs[0]["is_read"] == 1

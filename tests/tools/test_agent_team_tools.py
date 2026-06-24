"""Agent Team Tool 层单元测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.db.agent_team_db import AgentTeamDB
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
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_agent_team.db")


@pytest.fixture
def empty_db(db_path: str) -> str:
    """初始化数据库但不插入数据。"""
    db = AgentTeamDB(db_path)
    db.init_db()
    return db_path


@pytest.fixture
def initialized_db(db_path: str) -> str:
    """初始化数据库 + 预置当前 Agent 和一个接收方 Agent。"""
    db = AgentTeamDB(db_path)
    db.init_db()
    now = datetime.now(timezone.utc).isoformat()
    db.insert_agent(
        id=_TESTER_ID,
        name="Tester",
        desc="测试者",
        prompt="",
        status="online",
        created_at=now,
        updated_at=now,
    )
    db.insert_agent(
        id=_RECEIVER_ID,
        name="Receiver",
        desc="接收方",
        prompt="",
        status="online",
        created_at=now,
        updated_at=now,
    )
    return db_path


@pytest.fixture
def agent_ctx(empty_db: str) -> str:
    """未预置数据的上下文，返回 db_path。"""
    set_agent_team_context(empty_db, _TESTER_ID)
    yield empty_db
    set_agent_team_context(None, None)


@pytest.fixture
def populated_ctx(initialized_db: str) -> str:
    """已预置接收方 + 上下文已注入，返回 db_path。"""
    set_agent_team_context(initialized_db, _TESTER_ID)
    yield initialized_db
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
    async def test_send_success(self, populated_ctx: str):
        result = await send_message(to_agent_id=_RECEIVER_ID, content="hello team")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "message_id" in data
        assert "created_at" in data

        # 验证消息确实存到了 DB
        db = AgentTeamDB(populated_ctx)
        msgs, total = db.list_messages(_RECEIVER_ID, 10, 0)
        assert total == 1
        assert msgs[0]["content"] == "hello team"
        assert msgs[0]["sender_id"] == _TESTER_ID

    @pytest.mark.asyncio
    async def test_send_empty_content(self, populated_ctx: str):
        data = json.loads(await send_message(to_agent_id=_RECEIVER_ID, content=""))
        assert data["status"] == "error" and data["code"] == "EMPTY_CONTENT"

    @pytest.mark.asyncio
    async def test_send_whitespace_content(self, populated_ctx: str):
        data = json.loads(await send_message(to_agent_id=_RECEIVER_ID, content="   \n\t"))
        assert data["status"] == "error" and data["code"] == "EMPTY_CONTENT"

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_agent(self, populated_ctx: str):
        data = json.loads(await send_message(to_agent_id="nonexistent", content="hello"))
        assert data["status"] == "error" and data["code"] == "AGENT_NOT_FOUND"


# ── receive_message ────────────────────────────────────────────────────────


class TestReceiveMessageTool:
    """receive_message 测试。

    当前上下文是 _TESTER_ID，所以需要往 _TESTER_ID 的信箱中塞消息。
    populated_ctx fixture 中的 DB 里有一个 _RECEIVER_ID Agent，
    但 _TESTER_ID 本身并不在 DB 中（没有 row），不过能收消息（收消息不校验 receiver 是否存在）。
    """

    def _insert_test_message(self, db_path: str, content: str, idx: int = 0) -> str:
        db = AgentTeamDB(db_path)
        mid = f"test-msg-{idx}"
        now = datetime.now(timezone.utc).isoformat()
        db.insert_message(id=mid, sender_id=_RECEIVER_ID, receiver_id=_TESTER_ID, content=content, created_at=now)
        return mid

    @pytest.mark.asyncio
    async def test_receive_empty_inbox(self, populated_ctx: str):
        data = json.loads(await receive_message())
        assert data["status"] == "ok"
        assert data["messages"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_receive_pagination(self, populated_ctx: str):
        for i in range(5):
            self._insert_test_message(populated_ctx, f"content-{i}", i)

        page1 = json.loads(await receive_message(limit=2, offset=0))
        assert page1["status"] == "ok"
        assert len(page1["messages"]) == 2
        assert page1["total"] == 5

        page2 = json.loads(await receive_message(limit=2, offset=2))
        assert page2["status"] == "ok"
        assert len(page2["messages"]) == 2
        assert page2["total"] == 5

    @pytest.mark.asyncio
    async def test_receive_mark_as_read(self, populated_ctx: str):
        self._insert_test_message(populated_ctx, "mark-read-test", 0)
        # 接收（内部触发 mark_as_read）
        await receive_message()

        # 验证 DB 中消息已被标记为已读
        db = AgentTeamDB(populated_ctx)
        msgs, _ = db.list_messages(_TESTER_ID, 10, 0)
        assert msgs[0]["is_read"] == 1

    @pytest.mark.asyncio
    async def test_receive_unread_only(self, populated_ctx: str):
        self._insert_test_message(populated_ctx, "已读", 0)
        self._insert_test_message(populated_ctx, "未读", 1)
        # 第一次收全部消息（标记已读）
        await receive_message()
        # 再插入一条未读
        self._insert_test_message(populated_ctx, "新未读", 2)

        r = json.loads(await receive_message(unread_only=True))
        assert r["status"] == "ok"
        assert r["total"] == 1
        assert r["messages"][0]["content"] == "新未读"


# ── get_contacts ───────────────────────────────────────────────────────────


class TestGetContactsTool:
    @pytest.mark.asyncio
    async def test_get_contacts_excludes_current(self, populated_ctx: str):
        data = json.loads(await get_contacts())
        assert data["status"] == "ok"
        ids = {c["id"] for c in data["contacts"]}
        assert _TESTER_ID not in ids

    @pytest.mark.asyncio
    async def test_get_contacts_filter_by_status(self, populated_ctx: str):
        data = json.loads(await get_contacts(status="online"))
        assert data["status"] == "ok"
        assert all(c["status"] == "online" for c in data["contacts"])

    @pytest.mark.asyncio
    async def test_get_contacts_invalid_status(self, populated_ctx: str):
        data = json.loads(await get_contacts(status="invalid"))
        assert data["status"] == "error" and data["code"] == "INVALID_STATUS"


# ── get_contact_detail ─────────────────────────────────────────────────────


class TestGetContactDetailTool:
    @pytest.mark.asyncio
    async def test_get_detail_success(self, populated_ctx: str):
        data = json.loads(await get_contact_detail(agent_id=_RECEIVER_ID))
        assert data["status"] == "ok"
        assert data["agent"]["id"] == _RECEIVER_ID
        assert data["agent"]["name"] == "Receiver"
        assert data["agent"]["status"] == "online"

    @pytest.mark.asyncio
    async def test_get_detail_not_found(self, populated_ctx: str):
        data = json.loads(await get_contact_detail(agent_id="nonexistent"))
        assert data["status"] == "error" and data["code"] == "AGENT_NOT_FOUND"


# ── create_agent ───────────────────────────────────────────────────────────


class TestCreateAgentTool:
    @pytest.mark.asyncio
    async def test_create_success(self, agent_ctx: str):
        data = json.loads(await create_agent(name="NewAgent", desc="描述", prompt="提示"))
        assert data["status"] == "ok"
        assert data["agent"]["name"] == "NewAgent"
        assert "id" in data["agent"]
        assert data["agent"]["status"] == "offline"
        assert data["agent"]["desc"] == "描述"
        assert data["agent"]["prompt"] == "提示"

    @pytest.mark.asyncio
    async def test_create_duplicate_name(self, agent_ctx: str):
        await create_agent(name="UniqueAgent")
        data = json.loads(await create_agent(name="UniqueAgent"))
        assert data["status"] == "error" and data["code"] == "DUPLICATE_NAME"

    @pytest.mark.asyncio
    async def test_create_default_values(self, agent_ctx: str):
        data = json.loads(await create_agent(name="MinimalAgent"))
        assert data["status"] == "ok"
        assert data["agent"]["desc"] == ""
        assert data["agent"]["prompt"] == ""

    @pytest.mark.asyncio
    async def test_create_empty_name(self, agent_ctx: str):
        data = json.loads(await create_agent(name=""))
        assert data["status"] == "error" and data["code"] == "INVALID_PARAMETERS"

    @pytest.mark.asyncio
    async def test_create_whitespace_name(self, agent_ctx: str):
        data = json.loads(await create_agent(name="   "))
        assert data["status"] == "error" and data["code"] == "INVALID_PARAMETERS"


# ── delete_agent ───────────────────────────────────────────────────────────


class TestDeleteAgentTool:
    @pytest.mark.asyncio
    async def test_delete_success(self, agent_ctx: str):
        create_resp = json.loads(await create_agent(name="ToDelete"))
        target_id = create_resp["agent"]["id"]

        data = json.loads(await delete_agent(agent_id=target_id))
        assert data["status"] == "ok"
        assert data["deleted"] is True

        # 验证已不出现在通讯录
        contacts_resp = json.loads(await get_contacts())
        ids = [c["id"] for c in contacts_resp["contacts"]]
        assert target_id not in ids

    @pytest.mark.asyncio
    async def test_delete_not_found(self, agent_ctx: str):
        data = json.loads(await delete_agent(agent_id="nonexistent"))
        assert data["status"] == "error" and data["code"] == "AGENT_NOT_FOUND"


# ── 端到端 ─────────────────────────────────────────────────────────────────


class TestEndToEndFlow:
    @pytest.mark.asyncio
    async def test_send_and_receive_roundtrip(self, populated_ctx: str):
        """发送消息 → 接收消息 → 验证已读。"""
        # 1. _TESTER_ID 发消息给 _RECEIVER_ID
        send_resp = json.loads(await send_message(to_agent_id=_RECEIVER_ID, content="roundtrip"))
        assert send_resp["status"] == "ok"
        message_id = send_resp["message_id"]

        # 2. 切换到接收方上下文收消息
        set_agent_team_context(populated_ctx, _RECEIVER_ID)
        try:
            recv_resp = json.loads(await receive_message())
            assert recv_resp["status"] == "ok"
            assert recv_resp["total"] >= 1
            ids = [m["id"] for m in recv_resp["messages"]]
            assert message_id in ids
            for m in recv_resp["messages"]:
                if m["id"] == message_id:
                    assert m["content"] == "roundtrip"
                    # 返回的消息 is_read 是查询时的值（标记已读前的状态）
        finally:
            set_agent_team_context(populated_ctx, _TESTER_ID)

        # 3. 验证 DB 中已被标记为已读
        db = AgentTeamDB(populated_ctx)
        msgs, _ = db.list_messages(_RECEIVER_ID, 10, 0)
        assert msgs[0]["is_read"] == 1

    @pytest.mark.asyncio
    async def test_multi_agent_create_and_chat(self, agent_ctx: str):
        """创建两个新 Agent，互相发消息。"""
        # 创建 AgentA
        a = json.loads(await create_agent(name="AgentA", desc="A"))
        assert a["status"] == "ok"

        # 创建 AgentB
        b = json.loads(await create_agent(name="AgentB", desc="B"))
        assert b["status"] == "ok"
        agent_b_id = b["agent"]["id"]

        # A → B 发消息
        send_resp = json.loads(await send_message(to_agent_id=agent_b_id, content="hello from A"))
        assert send_resp["status"] == "ok"

        # 切换到 B 收消息
        set_agent_team_context(agent_ctx, agent_b_id)
        try:
            recv_resp = json.loads(await receive_message())
            assert recv_resp["status"] == "ok"
            assert recv_resp["total"] == 1
            assert recv_resp["messages"][0]["content"] == "hello from A"
            # is_read 在返回的消息中是 0（标记已读前的值）
        finally:
            set_agent_team_context(agent_ctx, _TESTER_ID)

        # 验证 DB 中已标记为已读
        db = AgentTeamDB(agent_ctx)
        msgs, _ = db.list_messages(agent_b_id, 10, 0)
        assert msgs[0]["is_read"] == 1

"""AgentTeamService 单元测试 — 使用 Fake AsyncSession 注入。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.db.models import Agent, Relay
from src.db.repositories import AgentRepository, RelayRepository
from src.services.agent_team import (
    AgentNotFoundError,
    AgentTeamService,
    DuplicateNameError,
    EmptyContentError,
    InvalidStatusError,
)


class _FakeSession:
    """最小化 fake AsyncSession，仅用于仓库层测试。

    仓库层在测试中直接操作内部数据结构，
    此 fake 仅占位 session 参数位置。
    """

    def __init__(self) -> None:
        self.agents: dict[str, dict] = {}
        self.messages: list[dict] = []
        self._name_index: dict[str, str] = {}

    async def get(self, model_class, ident: str) -> Any:
        return None  # 仓库层测试不使用 session.get

    async def execute(self, stmt) -> Any:
        return None  # 仓库层测试不使用 session.execute

    def add(self, instance) -> None:
        pass


class _FakeAgentRepo(AgentRepository):
    def __init__(self, fake_session: _FakeSession) -> None:
        super().__init__(fake_session)  # type: ignore[arg-type]
        self._fake = fake_session

    async def save(self, agent: Agent) -> dict[str, Any]:
        agent_dict = {
            "id": agent.id,
            "name": agent.name,
            "desc": agent.desc,
            "prompt": agent.prompt,
            "allowed_tools": agent.allowed_tools,
            "model": agent.model,
            "workspace": agent.workspace,
            "status": agent.status,
            "created_at": agent.created_at.isoformat(),
            "updated_at": agent.updated_at.isoformat(),
        }
        self._fake.agents[agent_dict["id"]] = agent_dict
        self._fake._name_index[agent_dict["name"]] = agent_dict["id"]
        return agent_dict

    async def get(self, agent_id):
        return self._fake.agents.get(agent_id)

    async def get_by_name(self, name):
        agent_id = self._fake._name_index.get(name)
        return self._fake.agents.get(agent_id) if agent_id else None

    async def list(self, exclude_id=None, status_filter=None):
        result = [a for aid, a in self._fake.agents.items() if aid != exclude_id]
        if status_filter is not None:
            result = [a for a in result if a["status"] == status_filter]
        return result

    async def delete(self, agent_id):
        if agent_id not in self._fake.agents:
            return False
        self._fake.agents[agent_id]["status"] = "deleted"
        return True


class _FakeMsgRepo(RelayRepository):
    def __init__(self, fake_session: _FakeSession) -> None:
        super().__init__(fake_session)  # type: ignore[arg-type]
        self._fake = fake_session

    async def save(self, relay: Relay) -> dict[str, Any]:
        msg = {
            "id": relay.id,
            "sender_id": relay.sender_id,
            "receiver_id": relay.receiver_id,
            "content": relay.content,
            "is_read": 1 if relay.is_read else 0,
            "created_at": relay.created_at.isoformat(),
        }
        self._fake.messages.append(msg)
        return msg

    async def list_by_receiver(self, receiver_id, limit, offset, unread_only=False):
        filtered = [m for m in self._fake.messages if m["receiver_id"] == receiver_id]
        if unread_only:
            filtered = [m for m in filtered if m["is_read"] == 0]
        total = len(filtered)
        filtered.sort(key=lambda m: m["created_at"], reverse=True)
        page = filtered[offset : offset + limit]
        result = []
        for m in page:
            msg = dict(m)
            sender = self._fake.agents.get(m["sender_id"])
            msg["sender_name"] = sender["name"] if sender else None
            result.append(msg)
        return (result, total)

    async def mark_as_read(self, message_ids):
        for msg in self._fake.messages:
            if msg["id"] in message_ids:
                msg["is_read"] = 1


class _FakeService(AgentTeamService):
    def __init__(self) -> None:
        self._fake = _FakeSession()
        self._agent_repo = _FakeAgentRepo(self._fake)
        self._msg_repo = _FakeMsgRepo(self._fake)


@pytest.fixture
def service() -> _FakeService:
    svc = _FakeService()
    now = datetime.now(timezone.utc)
    svc._agent_repo._fake.agents = {}
    svc._agent_repo._fake._name_index = {}
    # 预填充 3 个 Agent
    for aid, name, desc, prompt, status in [
        ("agent-1", "Architect", "架构师", "prompt1", "online"),
        ("agent-2", "Coder", "编码者", "prompt2", "online"),
        ("agent-3", "Reviewer", "审查者", "prompt3", "offline"),
    ]:
        svc._agent_repo._fake.agents[aid] = {
            "id": aid,
            "name": name,
            "desc": desc,
            "prompt": prompt,
            "allowed_tools": "",
            "model": "",
            "workspace": "",
            "status": status,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        svc._agent_repo._fake._name_index[name] = aid
    return svc


def _relay(id: str, content: str = "Hello") -> Relay:
    return Relay(
        id=id,
        sender_id="agent-1",
        receiver_id="agent-2",
        content=content,
        is_read=False,
        created_at=datetime.now(timezone.utc),
    )


class TestAgentTeamService:
    @pytest.mark.asyncio
    async def test_send_message_success(self, service: _FakeService) -> None:
        result = await service.send_message("agent-1", "agent-2", "Hello")
        assert "id" in result
        assert "created_at" in result
        assert len(service._fake.messages) == 1
        assert service._fake.messages[0]["content"] == "Hello"
        assert service._fake.messages[0]["sender_id"] == "agent-1"
        assert service._fake.messages[0]["receiver_id"] == "agent-2"

    @pytest.mark.asyncio
    async def test_send_message_empty_content(self, service: _FakeService) -> None:
        with pytest.raises(EmptyContentError):
            await service.send_message("agent-1", "agent-2", "")

    @pytest.mark.asyncio
    async def test_send_message_whitespace_content(self, service: _FakeService) -> None:
        with pytest.raises(EmptyContentError):
            await service.send_message("agent-1", "agent-2", "   \n\t")

    @pytest.mark.asyncio
    async def test_send_message_agent_not_found(self, service: _FakeService) -> None:
        with pytest.raises(AgentNotFoundError):
            await service.send_message("agent-1", "nonexistent-agent", "Hello")

    @pytest.mark.asyncio
    async def test_receive_message_success(self, service: _FakeService) -> None:
        await service._msg_repo.save(_relay("msg-1"))
        messages, total = await service.receive_message("agent-2", limit=20, offset=0)
        assert total == 1
        assert len(messages) == 1
        assert messages[0]["id"] == "msg-1"
        assert messages[0]["sender_name"] == "Architect"

    @pytest.mark.asyncio
    async def test_receive_message_marks_as_read(self, service: _FakeService) -> None:
        await service._msg_repo.save(_relay("msg-1"))
        await service.receive_message("agent-2", limit=20, offset=0)
        for m in service._fake.messages:
            if m["id"] == "msg-1":
                assert m["is_read"] == 1

    @pytest.mark.asyncio
    async def test_receive_message_with_limit_offset(self, service: _FakeService) -> None:
        for i in range(5):
            await service._msg_repo.save(_relay(f"msg-{i}", f"content-{i}"))
        page1, total = await service.receive_message("agent-2", limit=2, offset=0)
        assert total == 5
        assert len(page1) == 2

        page2, total = await service.receive_message("agent-2", limit=2, offset=2)
        assert total == 5
        assert len(page2) == 2

    @pytest.mark.asyncio
    async def test_receive_message_receiver_not_found(self, service: _FakeService) -> None:
        with pytest.raises(AgentNotFoundError):
            await service.receive_message("nonexistent-agent")

    @pytest.mark.asyncio
    async def test_receive_message_sender_deleted(self, service: _FakeService) -> None:
        await service._agent_repo.delete("agent-1")
        await service._msg_repo.save(_relay("msg-1"))
        messages, total = await service.receive_message("agent-2")
        assert total == 1
        assert messages[0]["sender_name"] == "Architect"

    @pytest.mark.asyncio
    async def test_receive_message_unread_only(self, service: _FakeService) -> None:
        await service._msg_repo.save(_relay("msg-1", "已读"))
        await service._msg_repo.save(_relay("msg-2", "未读"))
        await service._msg_repo.mark_as_read(["msg-1"])
        messages, total = await service.receive_message("agent-2", limit=20, offset=0, unread_only=True)
        assert total == 1
        assert messages[0]["id"] == "msg-2"

    @pytest.mark.asyncio
    async def test_get_contacts_all(self, service: _FakeService) -> None:
        contacts = await service.get_contacts("agent-1")
        assert len(contacts) == 2
        contact_ids = {c["id"] for c in contacts}
        assert "agent-1" not in contact_ids
        assert "agent-2" in contact_ids
        assert "agent-3" in contact_ids

    @pytest.mark.asyncio
    async def test_get_contacts_excludes_deleted(self, service: _FakeService) -> None:
        await service._agent_repo.delete("agent-2")
        contacts = await service.get_contacts("agent-1")
        assert len(contacts) == 1
        assert contacts[0]["id"] == "agent-3"

    @pytest.mark.asyncio
    async def test_get_contacts_status_filter(self, service: _FakeService) -> None:
        contacts = await service.get_contacts("agent-1", status_filter="offline")
        assert len(contacts) == 1
        assert contacts[0]["id"] == "agent-3"

    @pytest.mark.asyncio
    async def test_get_contacts_invalid_status(self, service: _FakeService) -> None:
        with pytest.raises(InvalidStatusError):
            await service.get_contacts("agent-1", status_filter="invalid")

    @pytest.mark.asyncio
    async def test_get_contacts_deleted_status_filter(self, service: _FakeService) -> None:
        with pytest.raises(InvalidStatusError):
            await service.get_contacts("agent-1", status_filter="deleted")

    @pytest.mark.asyncio
    async def test_get_contact_detail_success(self, service: _FakeService) -> None:
        detail = await service.get_contact_detail("agent-1")
        assert detail["id"] == "agent-1"
        assert detail["name"] == "Architect"
        assert detail["desc"] == "架构师"
        assert detail["status"] == "online"

    @pytest.mark.asyncio
    async def test_get_contact_detail_not_found(self, service: _FakeService) -> None:
        with pytest.raises(AgentNotFoundError):
            await service.get_contact_detail("nonexistent-agent")

    @pytest.mark.asyncio
    async def test_create_agent_success(self, service: _FakeService) -> None:
        agent = await service.create_agent(
            "NewAgent",
            desc="新 Agent",
            prompt="prompt-new",
            allowed_tools="tool1,tool2",
            model="gpt-4",
            workspace="/ws",
        )
        assert agent["name"] == "NewAgent"
        assert agent["desc"] == "新 Agent"
        assert agent["prompt"] == "prompt-new"
        assert agent["allowed_tools"] == "tool1,tool2"
        assert agent["model"] == "gpt-4"
        assert agent["workspace"] == "/ws"
        assert agent["status"] == "offline"
        assert "id" in agent
        stored = await service._agent_repo.get(agent["id"])
        assert stored == agent

    @pytest.mark.asyncio
    async def test_create_agent_empty_name(self, service: _FakeService) -> None:
        with pytest.raises(ValueError, match="Agent name is required"):
            await service.create_agent("")

    @pytest.mark.asyncio
    async def test_create_agent_whitespace_name(self, service: _FakeService) -> None:
        with pytest.raises(ValueError, match="Agent name is required"):
            await service.create_agent("   ")

    @pytest.mark.asyncio
    async def test_create_agent_duplicate_name(self, service: _FakeService) -> None:
        with pytest.raises(DuplicateNameError):
            await service.create_agent("Architect")

    @pytest.mark.asyncio
    async def test_delete_agent_success(self, service: _FakeService) -> None:
        result = await service.delete_agent("agent-1")
        assert result is True
        assert service._fake.agents["agent-1"]["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_agent_not_found(self, service: _FakeService) -> None:
        with pytest.raises(AgentNotFoundError):
            await service.delete_agent("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_agent_preserves_record(self, service: _FakeService) -> None:
        await service.delete_agent("agent-1")
        agent = await service._agent_repo.get("agent-1")
        assert agent is not None
        assert agent["status"] == "deleted"
        assert agent["name"] == "Architect"

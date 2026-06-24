from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.core.agent_team import (
    AgentNotFoundError,
    AgentTeamService,
    DuplicateNameError,
    EmptyContentError,
    InvalidStatusError,
)


class FakeAgentTeamDB:
    """在内存字典中模拟 AgentTeamDB 行为，接口与真实 DB 层一致。"""

    def __init__(self) -> None:
        self.agents: dict[str, dict] = {}
        self.messages: list[dict] = []
        self._name_index: dict[str, str] = {}

    def get_agent(self, agent_id: str) -> dict | None:
        return self.agents.get(agent_id)

    def get_agent_by_name(self, name: str) -> dict | None:
        agent_id = self._name_index.get(name)
        return self.agents.get(agent_id) if agent_id else None

    def insert_agent(
        self,
        id: str,
        name: str,
        desc: str,
        prompt: str,
        status: str,
        created_at: str,
        updated_at: str,
    ) -> dict:
        agent = {
            "id": id,
            "name": name,
            "desc": desc,
            "prompt": prompt,
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
        }
        self.agents[id] = agent
        self._name_index[name] = id
        return agent

    def list_agents(
        self,
        exclude_id: str | None = None,
        status_filter: str | None = None,
    ) -> list[dict]:
        result = [a for aid, a in self.agents.items() if aid != exclude_id]
        # 不默认过滤 deleted（匹配真实 DB 行为）
        if status_filter is not None:
            result = [a for a in result if a["status"] == status_filter]
        return result

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id not in self.agents:
            return False
        self.agents[agent_id]["status"] = "deleted"
        return True

    def insert_message(
        self,
        id: str,
        sender_id: str,
        receiver_id: str,
        content: str,
        created_at: str,
    ) -> dict:
        msg = {
            "id": id,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "content": content,
            "is_read": 0,
            "created_at": created_at,
        }
        self.messages.append(msg)
        return msg

    def list_messages(
        self,
        receiver_id: str,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> tuple[list[dict], int]:
        filtered = [m for m in self.messages if m["receiver_id"] == receiver_id]
        if unread_only:
            filtered = [m for m in filtered if m["is_read"] == 0]
        total = len(filtered)
        filtered.sort(key=lambda m: m["created_at"], reverse=True)
        page = filtered[offset : offset + limit]
        # 添加 sender_name（模拟真实 DB 的 LEFT JOIN 行为）
        result = []
        for m in page:
            msg = dict(m)
            sender = self.agents.get(m["sender_id"])
            msg["sender_name"] = sender["name"] if sender else None
            result.append(msg)
        return (result, total)

    def mark_as_read(self, message_ids: list[str]) -> None:
        for msg in self.messages:
            if msg["id"] in message_ids:
                msg["is_read"] = 1

    def close(self) -> None:
        pass


class TestAgentTeamService:
    """AgentTeamService 单元测试 — 使用 Fake DB 注入。"""

    @pytest.fixture
    def db(self) -> FakeAgentTeamDB:
        """创建预填充 3 个 Agent 的 fake DB。"""
        fake = FakeAgentTeamDB()
        now = datetime.now(timezone.utc).isoformat()
        fake.insert_agent("agent-1", "Architect", "架构师", "prompt1", "online", now, now)
        fake.insert_agent("agent-2", "Coder", "编码者", "prompt2", "online", now, now)
        fake.insert_agent("agent-3", "Reviewer", "审查者", "prompt3", "offline", now, now)
        return fake

    @pytest.fixture
    def service(self, db: FakeAgentTeamDB) -> AgentTeamService:
        return AgentTeamService(db)

    # ── send_message ────────────────────────────────────────────────────────

    def test_send_message_success(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """正常发送消息。"""
        result = service.send_message("agent-1", "agent-2", "Hello")
        assert "id" in result
        assert "created_at" in result
        assert len(db.messages) == 1
        assert db.messages[0]["content"] == "Hello"
        assert db.messages[0]["sender_id"] == "agent-1"
        assert db.messages[0]["receiver_id"] == "agent-2"

    def test_send_message_empty_content(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """content 为空字符串抛 EmptyContentError。"""
        with pytest.raises(EmptyContentError):
            service.send_message("agent-1", "agent-2", "")

    def test_send_message_whitespace_content(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """content 纯空白字符抛 EmptyContentError。"""
        with pytest.raises(EmptyContentError):
            service.send_message("agent-1", "agent-2", "   \n\t")

    def test_send_message_agent_not_found(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """目标 Agent 不存在抛 AgentNotFoundError。"""
        with pytest.raises(AgentNotFoundError):
            service.send_message("agent-1", "nonexistent-agent", "Hello")

    # ── receive_message ─────────────────────────────────────────────────────

    def test_receive_message_success(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """正常收消息，返回 (messages, total)，含 sender_name。"""
        db.insert_message("msg-1", "agent-1", "agent-2", "Hello", "2026-06-24T12:00:00")
        messages, total = service.receive_message("agent-2", limit=20, offset=0)
        assert total == 1
        assert len(messages) == 1
        assert messages[0]["id"] == "msg-1"
        assert messages[0]["sender_name"] == "Architect"

    def test_receive_message_marks_as_read(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """收消息后自动标记返回的消息为已读（验证存储层更新）。"""
        db.insert_message("msg-1", "agent-1", "agent-2", "Hello", "2026-06-24T12:00:00")
        service.receive_message("agent-2", limit=20, offset=0)
        # 验证存储中的消息已被标记为已读（返回的 dict 是副本不受影响）
        for m in db.messages:
            if m["id"] == "msg-1":
                assert m["is_read"] == 1

    def test_receive_message_with_limit_offset(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """分页查询返回正确页的消息和总数。"""
        for i in range(5):
            db.insert_message(
                f"msg-{i}",
                "agent-1",
                "agent-2",
                f"content-{i}",
                f"2026-06-24T12:0{i}:00",
            )
        page1, total = service.receive_message("agent-2", limit=2, offset=0)
        assert total == 5
        assert len(page1) == 2
        assert page1[0]["id"] == "msg-4"  # 按 created_at DESC

        page2, total = service.receive_message("agent-2", limit=2, offset=2)
        assert total == 5
        assert len(page2) == 2

    def test_receive_message_receiver_not_found(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """receiver Agent 不存在时抛 AgentNotFoundError。"""
        with pytest.raises(AgentNotFoundError):
            service.receive_message("nonexistent-agent")

    def test_receive_message_sender_deleted(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """sender 被软删除后，消息的 sender_name 仍然有效。"""
        db.delete_agent("agent-1")
        db.insert_message("msg-1", "agent-1", "agent-2", "Hello", "2026-06-24T12:00:00")
        messages, total = service.receive_message("agent-2")
        assert total == 1
        assert messages[0]["sender_name"] == "Architect"

    def test_receive_message_unread_only(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """只查询未读消息。"""
        db.insert_message("msg-1", "agent-1", "agent-2", "已读", "2026-06-24T12:00:00")
        db.insert_message("msg-2", "agent-1", "agent-2", "未读", "2026-06-24T12:01:00")
        db.mark_as_read(["msg-1"])
        messages, total = service.receive_message("agent-2", limit=20, offset=0, unread_only=True)
        assert total == 1
        assert len(messages) == 1
        assert messages[0]["id"] == "msg-2"

    # ── get_contacts ────────────────────────────────────────────────────────

    def test_get_contacts_all(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """查询全部通讯录：排除当前 Agent，不包含 deleted。"""
        contacts = service.get_contacts("agent-1")
        assert len(contacts) == 2
        contact_ids = {c["id"] for c in contacts}
        assert "agent-1" not in contact_ids  # 排除自身
        assert "agent-2" in contact_ids
        assert "agent-3" in contact_ids

    def test_get_contacts_excludes_deleted(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """deleted 状态的 Agent 不出现通讯录中。"""
        db.delete_agent("agent-2")
        contacts = service.get_contacts("agent-1")
        assert len(contacts) == 1
        assert contacts[0]["id"] == "agent-3"

    def test_get_contacts_status_filter(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """按状态过滤通讯录。"""
        # agent-3 是 offline，其余是 online
        contacts = service.get_contacts("agent-1", status_filter="offline")
        assert len(contacts) == 1
        assert contacts[0]["id"] == "agent-3"
        assert contacts[0]["status"] == "offline"

    def test_get_contacts_invalid_status(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """非法 status_filter 抛 InvalidStatusError。"""
        with pytest.raises(InvalidStatusError):
            service.get_contacts("agent-1", status_filter="invalid")

    def test_get_contacts_deleted_status_filter(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """status_filter='deleted' 也应抛 InvalidStatusError（通讯录不应包含已删除）。"""
        with pytest.raises(InvalidStatusError):
            service.get_contacts("agent-1", status_filter="deleted")

    # ── get_contact_detail ──────────────────────────────────────────────────

    def test_get_contact_detail_success(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """查询 Agent 详情返回完整字典。"""
        detail = service.get_contact_detail("agent-1")
        assert detail["id"] == "agent-1"
        assert detail["name"] == "Architect"
        assert detail["desc"] == "架构师"
        assert detail["status"] == "online"

    def test_get_contact_detail_not_found(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """Agent 不存在抛 AgentNotFoundError。"""
        with pytest.raises(AgentNotFoundError):
            service.get_contact_detail("nonexistent-agent")

    # ── create_agent ────────────────────────────────────────────────────────

    def test_create_agent_success(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """正常创建 Agent，返回完整字典，status 默认为 offline。"""
        agent = service.create_agent("NewAgent", desc="新 Agent", prompt="prompt-new")
        assert agent["name"] == "NewAgent"
        assert agent["desc"] == "新 Agent"
        assert agent["prompt"] == "prompt-new"
        assert agent["status"] == "offline"
        assert "id" in agent
        assert "created_at" in agent
        assert "updated_at" in agent
        # 验证已存入 DB
        stored = db.get_agent(agent["id"])
        assert stored == agent

    def test_create_agent_empty_name(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """name 为空字符串抛 ValueError。"""
        with pytest.raises(ValueError, match="Agent name is required"):
            service.create_agent("")

    def test_create_agent_whitespace_name(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """name 纯空白字符抛 ValueError。"""
        with pytest.raises(ValueError, match="Agent name is required"):
            service.create_agent("   ")

    def test_create_agent_duplicate_name(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """同名 Agent 已存在抛 DuplicateNameError。"""
        with pytest.raises(DuplicateNameError):
            service.create_agent("Architect")  # 已存在的名称

    # ── delete_agent ────────────────────────────────────────────────────────

    def test_delete_agent_success(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """正常软删除返回 True，status 变为 deleted。"""
        result = service.delete_agent("agent-1")
        assert result is True
        assert db.agents["agent-1"]["status"] == "deleted"

    def test_delete_agent_not_found(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """Agent 不存在抛 AgentNotFoundError。"""
        with pytest.raises(AgentNotFoundError):
            service.delete_agent("nonexistent")

    def test_delete_agent_preserves_record(self, service: AgentTeamService, db: FakeAgentTeamDB) -> None:
        """软删除后仍可通过 get_agent 查询（status='deleted'）。"""
        service.delete_agent("agent-1")
        agent = db.get_agent("agent-1")
        assert agent is not None
        assert agent["status"] == "deleted"
        assert agent["id"] == "agent-1"
        assert agent["name"] == "Architect"

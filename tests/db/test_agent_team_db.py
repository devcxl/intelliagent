from __future__ import annotations

import sqlite3

import pytest

from src.db.agent_team_db import AgentTeamDB

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def db(tmp_path):
    """创建临时 SQLite 数据库并初始化。"""
    db_path = tmp_path / "test_agent_team.db"
    agent_db = AgentTeamDB(str(db_path))
    agent_db.init_db()
    yield agent_db
    agent_db.close()


# ── TestInitDB ──────────────────────────────────────────────────────────────


class TestInitDB:
    def test_create_tables_on_first_init(self, db: AgentTeamDB) -> None:
        """init_db() 调用后表应存在。"""
        tables = db._conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {row["name"] for row in tables}
        assert "agents" in table_names
        assert "agent_messages" in table_names

    def test_init_is_idempotent(self, db: AgentTeamDB) -> None:
        """两次 init_db() 不抛异常。"""
        db.init_db()  # 不应抛异常

    def test_indexes_exist(self, db: AgentTeamDB) -> None:
        """验证索引存在。"""
        indexes = db._conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        index_names = {row["name"] for row in indexes}
        assert "idx_agent_messages_inbox" in index_names
        assert "idx_agent_messages_sender" in index_names


# ── TestAgentCRUD ───────────────────────────────────────────────────────────


class TestAgentCRUD:
    _AGENT = {
        "id": "agent-001",
        "name": "CodeReviewer",
        "desc": "代码审查 Agent",
        "prompt": "你是代码审查专家",
        "status": "online",
        "created_at": "2026-06-24T12:00:00.000000",
        "updated_at": "2026-06-24T12:00:00.000000",
    }

    def test_insert_and_get_agent(self, db: AgentTeamDB) -> None:
        result = db.insert_agent(**self._AGENT)
        assert result["id"] == self._AGENT["id"]
        assert result["name"] == self._AGENT["name"]
        assert result["desc"] == self._AGENT["desc"]
        assert result["prompt"] == self._AGENT["prompt"]
        assert result["status"] == self._AGENT["status"]
        assert result["created_at"] == self._AGENT["created_at"]
        assert result["updated_at"] == self._AGENT["updated_at"]

        # get_agent 返回相同数据
        fetched = db.get_agent(self._AGENT["id"])
        assert fetched == result

    def test_get_agent_by_name_found(self, db: AgentTeamDB) -> None:
        db.insert_agent(**self._AGENT)
        fetched = db.get_agent_by_name(self._AGENT["name"])
        assert fetched is not None
        assert fetched["id"] == self._AGENT["id"]

    def test_get_agent_by_name_not_found(self, db: AgentTeamDB) -> None:
        assert db.get_agent_by_name("nonexistent") is None

    def test_list_agents_all(self, db: AgentTeamDB) -> None:
        agents = [
            {
                "id": "a1",
                "name": "Alpha",
                "desc": "d1",
                "prompt": "p1",
                "status": "online",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
            {
                "id": "a2",
                "name": "Beta",
                "desc": "d2",
                "prompt": "p2",
                "status": "offline",
                "created_at": "2026-01-02T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
            },
            {
                "id": "a3",
                "name": "Gamma",
                "desc": "d3",
                "prompt": "p3",
                "status": "busy",
                "created_at": "2026-01-03T00:00:00",
                "updated_at": "2026-01-03T00:00:00",
            },
        ]
        for a in agents:
            db.insert_agent(**a)

        result = db.list_agents()
        assert len(result) == 3
        # 按 name ASC 排序
        assert [r["name"] for r in result] == ["Alpha", "Beta", "Gamma"]

    def test_list_agents_exclude_id(self, db: AgentTeamDB) -> None:
        agents = [
            {
                "id": "a1",
                "name": "Alpha",
                "desc": "d1",
                "prompt": "p1",
                "status": "online",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
            {
                "id": "a2",
                "name": "Beta",
                "desc": "d2",
                "prompt": "p2",
                "status": "offline",
                "created_at": "2026-01-02T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
            },
        ]
        for a in agents:
            db.insert_agent(**a)

        result = db.list_agents(exclude_id="a1")
        assert len(result) == 1
        assert result[0]["id"] == "a2"

    def test_list_agents_status_filter(self, db: AgentTeamDB) -> None:
        agents = [
            {
                "id": "a1",
                "name": "Alpha",
                "desc": "d1",
                "prompt": "p1",
                "status": "online",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            },
            {
                "id": "a2",
                "name": "Beta",
                "desc": "d2",
                "prompt": "p2",
                "status": "offline",
                "created_at": "2026-01-02T00:00:00",
                "updated_at": "2026-01-02T00:00:00",
            },
            {
                "id": "a3",
                "name": "Gamma",
                "desc": "d3",
                "prompt": "p3",
                "status": "online",
                "created_at": "2026-01-03T00:00:00",
                "updated_at": "2026-01-03T00:00:00",
            },
        ]
        for a in agents:
            db.insert_agent(**a)

        result = db.list_agents(status_filter="online")
        assert len(result) == 2
        assert all(r["status"] == "online" for r in result)

    def test_list_agents_exclude_and_status_filter(self, db: AgentTeamDB) -> None:
        """同时使用 exclude_id 和 status_filter。"""
        for spec in [
            ("a1", "Alpha", "online"),
            ("a2", "Beta", "online"),
            ("a3", "Gamma", "offline"),
        ]:
            db.insert_agent(
                id=spec[0], name=spec[1], desc="", prompt="",
                status=spec[2], created_at="t", updated_at="t",
            )

        result = db.list_agents(exclude_id="a2", status_filter="online")
        assert len(result) == 1
        assert result[0]["id"] == "a1"

    def test_delete_agent_success(self, db: AgentTeamDB) -> None:
        db.insert_agent(**self._AGENT)
        result = db.delete_agent(self._AGENT["id"])
        assert result is True

        # 软删除后数据仍在，但 status 改变
        fetched = db.get_agent(self._AGENT["id"])
        assert fetched is not None
        assert fetched["status"] == "deleted"
        assert fetched["updated_at"] != self._AGENT["updated_at"]

    def test_delete_agent_not_found(self, db: AgentTeamDB) -> None:
        result = db.delete_agent("nonexistent")
        assert result is False

    def test_soft_deleted_agent_still_queryable(self, db: AgentTeamDB) -> None:
        db.insert_agent(**self._AGENT)
        db.delete_agent(self._AGENT["id"])
        fetched = db.get_agent(self._AGENT["id"])
        assert fetched is not None
        assert fetched["status"] == "deleted"


# ── TestMessageCRUD ─────────────────────────────────────────────────────────


class TestMessageCRUD:
    _SENDER = {
        "id": "agent-sender",
        "name": "Architect",
        "desc": "架构师 Agent",
        "prompt": "你是架构师",
        "status": "online",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }
    _RECEIVER = {
        "id": "agent-receiver",
        "name": "CodeReviewer",
        "desc": "审查 Agent",
        "prompt": "你是审查专家",
        "status": "online",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }

    @pytest.fixture(autouse=True)
    def setup_agents(self, db: AgentTeamDB) -> None:
        db.insert_agent(**self._SENDER)
        db.insert_agent(**self._RECEIVER)

    def test_insert_and_list_message(self, db: AgentTeamDB) -> None:
        msg = db.insert_message(
            id="msg-001",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="请审查代码",
            created_at="2026-06-24T12:05:00.000000",
        )
        assert msg["id"] == "msg-001"
        assert msg["sender_id"] == self._SENDER["id"]
        assert msg["receiver_id"] == self._RECEIVER["id"]
        assert msg["content"] == "请审查代码"
        assert msg["is_read"] == 0

        messages, total = db.list_messages(receiver_id=self._RECEIVER["id"], limit=10, offset=0)
        assert total == 1
        assert len(messages) == 1
        assert messages[0]["id"] == "msg-001"

    def test_list_messages_includes_sender_name(self, db: AgentTeamDB) -> None:
        db.insert_message(
            id="msg-001",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="你好",
            created_at="2026-06-24T12:05:00.000000",
        )
        messages, total = db.list_messages(receiver_id=self._RECEIVER["id"], limit=10, offset=0)
        assert total == 1
        assert messages[0]["sender_name"] == self._SENDER["name"]

    def test_list_messages_unread_only(self, db: AgentTeamDB) -> None:
        db.insert_message(
            id="m1",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="a",
            created_at="2026-06-24T12:00:00",
        )
        db.insert_message(
            id="m2",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="b",
            created_at="2026-06-24T12:01:00",
        )
        db.mark_as_read(["m1"])

        messages, total = db.list_messages(receiver_id=self._RECEIVER["id"], limit=10, offset=0, unread_only=True)
        assert total == 1
        assert messages[0]["id"] == "m2"

    def test_list_messages_sort_order(self, db: AgentTeamDB) -> None:
        db.insert_message(
            id="m1",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="first",
            created_at="2026-06-24T12:00:00",
        )
        db.insert_message(
            id="m2",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="second",
            created_at="2026-06-24T12:01:00",
        )
        db.insert_message(
            id="m3",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="third",
            created_at="2026-06-24T12:02:00",
        )

        messages, total = db.list_messages(receiver_id=self._RECEIVER["id"], limit=10, offset=0)
        assert total == 3
        # 按 created_at DESC 排序
        assert [m["id"] for m in messages] == ["m3", "m2", "m1"]

    def test_list_messages_pagination(self, db: AgentTeamDB) -> None:
        for i in range(5):
            db.insert_message(
                id=f"m{i}",
                sender_id=self._SENDER["id"],
                receiver_id=self._RECEIVER["id"],
                content=f"msg-{i}",
                created_at=f"2026-06-24T12:0{i}:00",
            )

        page1, total = db.list_messages(receiver_id=self._RECEIVER["id"], limit=2, offset=0)
        assert total == 5
        assert len(page1) == 2

        page2, total = db.list_messages(receiver_id=self._RECEIVER["id"], limit=2, offset=2)
        assert total == 5
        assert len(page2) == 2

    def test_list_messages_total_count(self, db: AgentTeamDB) -> None:
        for i in range(3):
            db.insert_message(
                id=f"m{i}",
                sender_id=self._SENDER["id"],
                receiver_id=self._RECEIVER["id"],
                content=f"msg-{i}",
                created_at=f"2026-06-24T12:0{i}:00",
            )

        _, total = db.list_messages(receiver_id=self._RECEIVER["id"], limit=1, offset=0)
        assert total == 3

    def test_mark_as_read(self, db: AgentTeamDB) -> None:
        db.insert_message(
            id="m1",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="a",
            created_at="2026-06-24T12:00:00",
        )
        db.insert_message(
            id="m2",
            sender_id=self._SENDER["id"],
            receiver_id=self._RECEIVER["id"],
            content="b",
            created_at="2026-06-24T12:01:00",
        )

        db.mark_as_read(["m1", "m2"])

        messages, _ = db.list_messages(receiver_id=self._RECEIVER["id"], limit=10, offset=0)
        assert all(m["is_read"] == 1 for m in messages)


# ── TestEdgeCases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_get_agent_nonexistent(self, db: AgentTeamDB) -> None:
        assert db.get_agent("nonexistent") is None

    def test_mark_as_read_empty_list(self, db: AgentTeamDB) -> None:
        db.mark_as_read([])  # 不应抛异常

    def test_insert_duplicate_id(self, db: AgentTeamDB) -> None:
        db.insert_agent(
            id="dup",
            name="first",
            desc="",
            prompt="",
            status="online",
            created_at="t",
            updated_at="t",
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_agent(
                id="dup",
                name="second",
                desc="",
                prompt="",
                status="online",
                created_at="t",
                updated_at="t",
            )

    def test_insert_duplicate_name(self, db: AgentTeamDB) -> None:
        db.insert_agent(
            id="a1",
            name="same",
            desc="",
            prompt="",
            status="online",
            created_at="t",
            updated_at="t",
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_agent(
                id="a2",
                name="same",
                desc="",
                prompt="",
                status="online",
                created_at="t",
                updated_at="t",
            )

    def test_insert_invalid_status(self, db: AgentTeamDB) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_agent(
                id="bad",
                name="bad",
                desc="",
                prompt="",
                status="invalid",
                created_at="t",
                updated_at="t",
            )

    def test_wal_mode_enabled(self, tmp_path) -> None:
        db_path = tmp_path / "test_wal.db"
        agent_db = AgentTeamDB(str(db_path))
        agent_db.init_db()
        try:
            row = agent_db._conn.execute("PRAGMA journal_mode").fetchone()
            # 返回 "wal" (不带收尾空格)
            assert row[0].lower() == "wal"
        finally:
            agent_db.close()

    def test_no_foreign_key_on_messages(self, db: AgentTeamDB) -> None:
        """确认 agent_messages 表无外键约束。"""
        create_sql = db._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='agent_messages'"
        ).fetchone()
        assert create_sql is not None
        table_ddl = create_sql["sql"].upper()
        assert "FOREIGN KEY" not in table_ddl
        assert "REFERENCES" not in table_ddl

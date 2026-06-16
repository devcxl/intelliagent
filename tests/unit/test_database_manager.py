#!/usr/bin/env python3
"""数据库初始化与兼容适配测试。"""

import sqlite3

from src.db.manager import DatabaseManager


async def test_database_manager_creates_parent_directory(tmp_path):
    db_path = tmp_path / "nested" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))

    await manager.initialize()

    assert db_path.parent.exists()
    assert db_path.exists()


async def test_database_manager_creates_pr3_core_tables(tmp_path):
    db_path = tmp_path / "schema" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))

    await manager.initialize()

    with sqlite3.connect(db_path) as connection:
        table_rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()

    table_names = {row[0] for row in table_rows}
    assert {"conversations", "messages"}.issubset(table_names)


async def test_database_manager_conversation_crud(tmp_path):
    db_path = tmp_path / "crud" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()

    created = await manager.create_conversation(
        conversation_id="conversation-1",
        title="测试 Conversation",
        task="测试任务",
        status="idle",
    )

    assert created["id"] == "conversation-1"
    assert created["logs"] == []

    fetched = await manager.get_conversation("conversation-1")
    assert fetched is not None
    assert fetched["title"] == "测试 Conversation"

    updated = await manager.update_conversation(
        "conversation-1",
        title="已更新",
        status="running",
        logs=[{"type": "thought", "message": "旧字段已废弃"}],
    )
    assert updated is True

    fetched_after_update = await manager.get_conversation("conversation-1")
    assert fetched_after_update is not None
    assert fetched_after_update["title"] == "已更新"
    assert fetched_after_update["status"] == "running"
    assert fetched_after_update["logs"] == []

    conversations = await manager.list_conversations()
    assert len(conversations) == 1

    await manager.save_message("conversation-1", "user", "hello")

    deleted = await manager.delete_conversation("conversation-1")
    assert deleted is True
    assert await manager.get_conversation("conversation-1") is None
    assert await manager.get_messages("conversation-1") == []

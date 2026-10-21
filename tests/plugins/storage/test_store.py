"""entry 写入、parent 链遍历与 append-only 不变量。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.plugins.storage import EntryNotFoundError, MessagePayload, StorageError, StorageStore


async def test_append_entry_round_trip(store: StorageStore) -> None:
    entry = await store.append_entry("custom", {"note": "hello", "count": 2})

    loaded = await store.get_entry(entry.id)

    assert loaded == entry
    assert loaded is not None
    assert loaded.parent_id is None
    assert loaded.type == "custom"
    assert loaded.payload == {"note": "hello", "count": 2}
    assert loaded.created_at is not None


async def test_get_entry_returns_none_for_unknown_id(store: StorageStore) -> None:
    assert await store.get_entry("missing") is None


async def test_append_message_persists_message_payload(store: StorageStore) -> None:
    payload = MessagePayload(role="assistant", content="hi", tool_name="read", tool_args='{"path": "a"}')

    entry = await store.append_message(payload)

    assert entry.type == "message"
    assert MessagePayload.model_validate(entry.payload) == payload


async def test_parent_links_form_chain(store: StorageStore) -> None:
    root = await store.append_entry("message", {"n": 0})
    child = await store.append_entry("message", {"n": 1}, parent_id=root.id)
    grandchild = await store.append_entry("message", {"n": 2}, parent_id=child.id)

    path = await store.branch_path(grandchild.id)

    assert [entry.id for entry in path] == [root.id, child.id, grandchild.id]


async def test_branch_path_keeps_only_selected_branch(store: StorageStore) -> None:
    root = await store.append_entry("message", {"n": 0})
    kept = await store.append_entry("message", {"kept": True}, parent_id=root.id)
    abandoned = await store.append_entry("message", {"abandoned": True}, parent_id=root.id)

    path = await store.branch_path(kept.id)

    assert [entry.id for entry in path] == [root.id, kept.id]
    # 弃用分支的原始记录仍然完整可查
    assert await store.get_entry(abandoned.id) is not None


async def test_append_entry_rejects_unknown_parent(store: StorageStore) -> None:
    with pytest.raises(EntryNotFoundError, match="parent"):
        await store.append_entry("message", {}, parent_id="missing")


async def test_branch_path_rejects_unknown_entry(store: StorageStore) -> None:
    with pytest.raises(EntryNotFoundError):
        await store.branch_path("missing")


async def test_append_entry_rejects_empty_type(store: StorageStore) -> None:
    with pytest.raises(StorageError, match="type"):
        await store.append_entry("", {})


class TestAppendOnly:
    """append-only 不变量：无删除/更新 API，数据库层拒绝 UPDATE/DELETE。"""

    async def test_store_exposes_no_delete_or_update_api(self, store: StorageStore) -> None:
        forbidden = sorted(name for name in dir(store) if any(word in name for word in ("delete", "remove", "update")))
        assert forbidden == []

    async def test_database_rejects_raw_update_and_delete(self, store: StorageStore, tmp_path: Path) -> None:
        entry = await store.append_entry("message", {"n": 1})

        raw = sqlite3.connect(tmp_path / "storage.db")
        try:
            statements = (
                ("UPDATE entries SET payload = ? WHERE id = ?", ('{"tampered": true}', entry.id)),
                ("DELETE FROM entries WHERE id = ?", (entry.id,)),
            )
            for statement, params in statements:
                with pytest.raises(sqlite3.DatabaseError, match="append-only"):
                    raw.execute(statement, params)
            raw.commit()
        finally:
            raw.close()

        loaded = await store.get_entry(entry.id)
        assert loaded == entry
        assert loaded is not None
        assert loaded.payload == {"n": 1}

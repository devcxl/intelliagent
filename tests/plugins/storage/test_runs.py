"""Run 记录：run 元数据 + 以追加状态 entry 表达的生命周期更新。"""

from __future__ import annotations

import pytest

from src.plugins.storage import ENTRY_TYPE_RUN, ENTRY_TYPE_RUN_STATUS, StorageError, StorageStore


async def test_append_run_persists_run_record(store: StorageStore) -> None:
    record = await store.append_run(model="gpt-x")

    assert record.status == "running"
    assert record.model == "gpt-x"
    assert record.token_usage is None
    assert record.created_at == record.updated_at

    assert await store.get_run(record.run_id) == record
    entry = await store.get_entry(record.run_id)
    assert entry is not None
    assert entry.type == ENTRY_TYPE_RUN


async def test_run_updates_are_appended_status_entries(store: StorageStore) -> None:
    record = await store.append_run(model="gpt-x")

    updated = await store.append_run_status(
        record.run_id, status="completed", token_usage={"prompt_tokens": 10, "completion_tokens": 5}
    )

    assert updated.status == "completed"
    assert updated.token_usage == {"prompt_tokens": 10, "completion_tokens": 5}
    assert updated.updated_at >= updated.created_at

    entries = await store.run_entries(record.run_id)
    assert [entry.type for entry in entries] == [ENTRY_TYPE_RUN, ENTRY_TYPE_RUN_STATUS]
    # run entry 原始记录未被改写，状态更新以追加 entry 表达
    assert entries[0].payload == {"status": "running", "model": "gpt-x"}
    assert entries[1].payload == {"status": "completed", "token_usage": {"prompt_tokens": 10, "completion_tokens": 5}}


async def test_run_status_history_is_preserved(store: StorageStore) -> None:
    record = await store.append_run(model="gpt-x")

    await store.append_run_status(record.run_id, status="running", token_usage={"prompt_tokens": 3})
    projected = await store.append_run_status(record.run_id, status="failed")

    assert projected.status == "failed"
    # 未上报新用量时保留最近一次上报的累计用量
    assert projected.token_usage == {"prompt_tokens": 3}

    entries = await store.run_entries(record.run_id)
    assert [entry.payload["status"] for entry in entries] == ["running", "running", "failed"]


async def test_get_run_returns_none_for_unknown_run(store: StorageStore) -> None:
    assert await store.get_run("missing") is None


async def test_get_run_rejects_non_run_entry(store: StorageStore) -> None:
    entry = await store.append_entry("message", {})

    with pytest.raises(StorageError, match="not a run"):
        await store.get_run(entry.id)

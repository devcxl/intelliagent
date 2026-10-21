"""Compactor 的会话边界：同一数据库内按会话根续接，headless 新会话不串上下文。"""

from __future__ import annotations

import pytest

from src.core.compaction import CompactionError, Compactor
from src.core.token_counting import TokenCounter
from src.plugins.storage import StorageStore
from tests.core.compaction_support import user
from tests.core.engine_support import FakeLLM


def make_compactor(
    store: StorageStore,
    *,
    conversation_root_id: str,
    resume: bool = True,
) -> Compactor:
    return Compactor(
        FakeLLM(),
        store,
        model="fake/model",
        counter=TokenCounter(),
        context_window=1_000_000,
        conversation_root_id=conversation_root_id,
        resume=resume,
    )


async def test_conversation_root_resumes_its_own_chain(store: StorageStore) -> None:
    compactor = make_compactor(store, conversation_root_id="tui")
    await compactor.sync_messages([user("a")])

    resumed = await Compactor.resume(
        FakeLLM(),
        store,
        model="fake/model",
        counter=TokenCounter(),
        context_window=1_000_000,
        conversation_root_id="tui",
    )

    assert resumed.leaf_entry_id == compactor.leaf_entry_id


async def test_new_conversation_starts_at_its_own_root(store: StorageStore) -> None:
    first = make_compactor(store, conversation_root_id="tui")
    await first.sync_messages([user("tui message")])

    headless = make_compactor(store, conversation_root_id="headless-1", resume=False)
    await headless.sync_messages([user("headless message")])

    assert await store.latest_leaf_in("tui") == first.leaf_entry_id
    assert await store.latest_leaf_in("headless-1") == headless.leaf_entry_id
    assert first.leaf_entry_id != headless.leaf_entry_id


async def test_new_conversation_rejects_existing_entries(store: StorageStore) -> None:
    existing = make_compactor(store, conversation_root_id="tui")
    await existing.sync_messages([user("a")])

    with pytest.raises(CompactionError, match="already has entries"):
        await make_compactor(store, conversation_root_id="tui", resume=False).sync_messages([])

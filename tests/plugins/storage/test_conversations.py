"""会话根与 latest_leaf_in：多会话共享一个数据库时的链定位语义。"""

from __future__ import annotations

import pytest

from src.plugins.storage import ENTRY_TYPE_CONVERSATION, EntryNotFoundError, StorageError, StorageStore


async def test_ensure_conversation_is_idempotent(store: StorageStore) -> None:
    root = await store.ensure_conversation("tui")
    again = await store.ensure_conversation("tui")

    assert root.id == "tui"
    assert root.type == ENTRY_TYPE_CONVERSATION
    assert again == root


async def test_latest_leaf_in_tracks_message_and_compaction_chain(store: StorageStore) -> None:
    root = await store.ensure_conversation("tui")
    first = await store.append_chat_message({"role": "user", "content": "a"}, parent_id=root.id)
    second = await store.append_chat_message({"role": "assistant", "content": "b"}, parent_id=first)

    assert await store.latest_leaf_in("tui") == second

    compaction = await store.append_compaction(
        summary="s",
        first_kept_entry_id=first,
        prompt_checkpoint={},
        parent_id=second,
    )
    assert await store.latest_leaf_in("tui") == compaction.entry_id


async def test_latest_leaf_in_rejects_fork(store: StorageStore) -> None:
    root = await store.ensure_conversation("tui")
    await store.append_chat_message({"role": "user", "content": "a"}, parent_id=root.id)
    await store.append_chat_message({"role": "user", "content": "b"}, parent_id=root.id)

    with pytest.raises(StorageError, match="branched"):
        await store.latest_leaf_in("tui")


async def test_ensure_conversation_rejects_non_conversation_entry(store: StorageStore) -> None:
    message = await store.append_entry("message", {"role": "user", "content": "a"})

    with pytest.raises(StorageError, match="not a conversation"):
        await store.ensure_conversation(message.id)


async def test_latest_leaf_in_unknown_conversation_raises(store: StorageStore) -> None:
    with pytest.raises(EntryNotFoundError, match="missing"):
        await store.latest_leaf_in("missing")

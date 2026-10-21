"""compaction 记录 round-trip 与投影查询（#59 消费的查询面）。"""

from __future__ import annotations

import pytest

from src.plugins.storage import (
    ENTRY_TYPE_COMPACTION,
    ENTRY_TYPE_MESSAGE,
    CompactionRecord,
    EntryNotFoundError,
    StorageError,
    StorageStore,
)


async def test_compaction_round_trip(store: StorageStore) -> None:
    kept = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 1})
    checkpoint = {"system_prompt": "You are IntelliAgent.", "tools": ["read", "bash"]}

    record = await store.append_compaction(
        summary="前情已总结", first_kept_entry_id=kept.id, prompt_checkpoint=checkpoint
    )

    assert record.summary == "前情已总结"
    assert record.first_kept_entry_id == kept.id
    assert record.prompt_checkpoint == checkpoint

    loaded = await store.get_entry(record.entry_id)
    assert loaded is not None
    assert loaded.type == ENTRY_TYPE_COMPACTION
    assert CompactionRecord.from_entry(loaded) == record


async def test_append_compaction_requires_existing_first_kept(store: StorageStore) -> None:
    with pytest.raises(EntryNotFoundError, match="first_kept_entry_id"):
        await store.append_compaction(summary="s", first_kept_entry_id="missing", prompt_checkpoint={})


async def test_projection_without_compaction_returns_whole_path(store: StorageStore) -> None:
    root = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 1})
    tip = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 2}, parent_id=root.id)

    projection = await store.projection(tip.id)

    assert projection.compaction is None
    assert [entry.id for entry in projection.entries] == [root.id, tip.id]


async def test_projection_returns_summary_and_kept_segment(store: StorageStore) -> None:
    e1 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 1})
    e2 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 2}, parent_id=e1.id)
    e3 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 3}, parent_id=e2.id)
    e4 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 4}, parent_id=e3.id)
    compaction = await store.append_compaction(
        summary="前情已总结", first_kept_entry_id=e2.id, prompt_checkpoint={"system_prompt": "sp"}, parent_id=e4.id
    )
    e5 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 5}, parent_id=compaction.entry_id)

    projection = await store.projection(e5.id)

    assert projection.compaction is not None
    assert projection.compaction.summary == "前情已总结"
    assert projection.compaction.first_kept_entry_id == e2.id
    assert projection.compaction.prompt_checkpoint == {"system_prompt": "sp"}
    assert [entry.id for entry in projection.entries] == [e2.id, e3.id, e4.id, e5.id]
    # 被压缩的 entry 不在投影中，但原始记录仍完整可查（append-only）
    assert await store.get_entry(e1.id) == e1


async def test_projection_uses_latest_compaction(store: StorageStore) -> None:
    e1 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 1})
    e2 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 2}, parent_id=e1.id)
    e3 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 3}, parent_id=e2.id)
    first = await store.append_compaction(
        summary="s1", first_kept_entry_id=e2.id, prompt_checkpoint={}, parent_id=e3.id
    )
    e4 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 4}, parent_id=first.entry_id)
    second = await store.append_compaction(
        summary="s2", first_kept_entry_id=e3.id, prompt_checkpoint={}, parent_id=e4.id
    )
    e5 = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 5}, parent_id=second.entry_id)

    projection = await store.projection(e5.id)

    assert projection.compaction is not None
    assert projection.compaction.entry_id == second.entry_id
    # 更早的 compaction 记录由最新摘要取代、不进投影，但保留在库中
    assert [entry.id for entry in projection.entries] == [e3.id, e4.id, e5.id]
    assert await store.get_entry(e1.id) is not None
    assert await store.get_entry(first.entry_id) is not None


async def test_projection_rejects_first_kept_off_branch(store: StorageStore) -> None:
    root = await store.append_entry(ENTRY_TYPE_MESSAGE, {"n": 0})
    side = await store.append_entry(ENTRY_TYPE_MESSAGE, {"side": True}, parent_id=root.id)
    tip = await store.append_entry(ENTRY_TYPE_MESSAGE, {"tip": True}, parent_id=root.id)
    compaction = await store.append_compaction(
        summary="s", first_kept_entry_id=side.id, prompt_checkpoint={}, parent_id=tip.id
    )

    with pytest.raises(StorageError, match="first_kept_entry_id"):
        await store.projection(compaction.entry_id)

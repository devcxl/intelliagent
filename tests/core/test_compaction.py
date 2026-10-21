"""投影式压缩：切点选择、阈值触发、LLM 增量摘要、compaction 写入与投影回归（issue #59、pi-engine-principles §4）。

压缩不删除历史：只追加 compaction 记录（摘要 + first_kept_entry_id + prompt checkpoint），
发给模型的上下文每次请求从 storage.projection 现算。切点语义照搬 pi findCutPoint：
预算耗尽点吸附到有效切点（user/assistant，绝不孤儿 tool 结果），切在 turn 中间即 split turn，
其前缀用独立 prompt 单独总结。
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from src.core.compaction import CompactionError, CutPoint, TokenCounter, find_cut_point, summary_message
from src.core.compaction_prompts import (
    SPLIT_TURN_MARKER,
    SUMMARIZATION_SYSTEM_PROMPT,
    TURN_PREFIX_SUMMARIZATION_PROMPT,
    UPDATE_SUMMARIZATION_PROMPT,
)
from src.core.turn_hooks import NextTurnContext, RequestContext, TurnResult
from src.llm.stream import ChatMessage, Usage
from src.plugins.storage import StorageStore
from tests.core.compaction_support import (
    assistant,
    make_compactor,
    padding,
    summary_response,
    tool_call,
    tool_call_response,
    user,
)
from tests.core.engine_support import FakeLLM


def next_turn_context(messages: Sequence[ChatMessage]) -> NextTurnContext:
    """构造 turn 边界 hook 的输入快照（一个已完成的纯文本 turn）。"""
    return NextTurnContext(
        turn=2,
        result=TurnResult(turn=1, message=assistant("ok"), observations=()),
        model="fake/model",
        messages=tuple(messages),
        tools=(),
    )


class TestCutPoint:
    """纯函数切点计算：预算保留、有效切点吸附、split turn 判定。"""

    def test_cut_point_keeps_recent_budget_at_message_boundary(self) -> None:
        """从尾部累计到 keepRecentTokens 即定切点，落在预算耗尽处的消息边界。"""
        messages = [user(padding("m0")), user(padding("m1")), user(padding("m2"))]

        cut = find_cut_point(messages, keep_recent_tokens=250)

        assert cut == CutPoint(first_kept_index=2, turn_start_index=None, is_split_turn=False)

    def test_cut_point_never_starts_with_tool_result(self) -> None:
        """预算在 tool 结果处耗尽时向前吸附：tool 结果永远与它的 assistant tool_call 同侧保留。"""
        messages = [
            user(padding("m0")),
            assistant("", tool_calls=[tool_call("c1", '{"path": "a"}')]),
            {"role": "tool", "tool_call_id": "c1", "name": "rec", "content": padding("m2")},
            user(padding("m3")),
            assistant(padding("m4")),
        ]

        cut = find_cut_point(messages, keep_recent_tokens=250)

        assert cut == CutPoint(first_kept_index=3, turn_start_index=None, is_split_turn=False)
        assert messages[cut.first_kept_index]["role"] != "tool"

    def test_cut_point_at_user_message_is_not_split(self) -> None:
        """切点落在 user 消息即 turn 边界，不触发 split turn。"""
        messages = [user(padding("m0")), assistant(padding("m1")), user(padding("m2")), assistant(padding("m3"))]

        cut = find_cut_point(messages, keep_recent_tokens=150)

        assert cut == CutPoint(first_kept_index=2, turn_start_index=None, is_split_turn=False)

    def test_cut_point_marks_split_turn_when_cut_lands_mid_turn(self) -> None:
        """切在 assistant（turn 中间）即 split turn：turn 起点（user 消息）之前的完整 turn 进历史摘要。"""
        messages = [user(padding("m0")), assistant(padding("m1")), user(padding("m2")), assistant(padding("m3"))]

        cut = find_cut_point(messages, keep_recent_tokens=50)

        assert cut == CutPoint(first_kept_index=3, turn_start_index=2, is_split_turn=True)

    def test_cut_point_falls_back_behind_trailing_tool_results(self) -> None:
        """预算被尾部 tool 结果独占时退到最后一个有效切点：保 tool 配对优先于保预算。"""
        messages = [
            user(padding("m0")),
            assistant("", tool_calls=[tool_call("c1", '{"path": "a"}')]),
            {"role": "tool", "tool_call_id": "c1", "name": "rec", "content": padding("m2")},
            {"role": "tool", "tool_call_id": "c1", "name": "rec", "content": padding("m3")},
        ]

        cut = find_cut_point(messages, keep_recent_tokens=50)

        assert cut == CutPoint(first_kept_index=1, turn_start_index=0, is_split_turn=True)

    def test_find_cut_point_returns_none_without_valid_cut_points(self) -> None:
        """全是 tool 结果时没有有效切点（孤儿 tool 结果不可接受），无可压缩。"""
        tool_only: list[ChatMessage] = [
            {"role": "tool", "tool_call_id": "c1", "name": "rec", "content": padding("m0")},
        ]

        assert find_cut_point(tool_only, keep_recent_tokens=10) is None


class TestCompactionTrigger:
    """阈值触发：真实 usage + 尾部估算，超过 contextWindow - reserve 才压缩。"""

    async def test_no_compaction_below_threshold(self, store: StorageStore) -> None:
        llm = FakeLLM()
        counter = TokenCounter()
        compactor = make_compactor(llm, store, counter=counter, context_window=110_000)
        messages = [user(padding("OLD")), assistant(padding("OLD")), user(padding("KEEP"))]
        await compactor.persist_messages(messages)
        counter.record(Usage(prompt_tokens=1_000, completion_tokens=10, total_tokens=1_010), messages)

        update = await compactor.prepare_next_turn(next_turn_context(messages))

        assert update is None
        projection = await store.projection(compactor.leaf_entry_id)
        assert projection.compaction is None
        assert llm.requests == []

    async def test_threshold_trigger_uses_real_usage_plus_tail_estimate(self, store: StorageStore) -> None:
        """chars 估算仅 ~300 tokens 的样例能超阈值，只可能来自真实 usage；尾部新增消息计入估算。"""
        llm = FakeLLM()
        counter = TokenCounter()
        compactor = make_compactor(llm, store, counter=counter, context_window=110_000, keep_recent_tokens=100)
        covered = [user(padding("OLD-TASK"))]
        rest = [assistant(padding("OLD-WORK")), user(padding("KEEP"))]
        await compactor.persist_messages(covered)
        counter.record(Usage(prompt_tokens=100_000, completion_tokens=10, total_tokens=100_010), covered)
        await compactor.persist_messages(rest)
        llm.enqueue(*summary_response("SUMMARY-1"))

        assert counter.estimate([*covered, *rest]) == 100_200  # 100_000 + 2×100 chars 估算
        update = await compactor.prepare_next_turn(next_turn_context([*covered, *rest]))

        assert update is None
        projection = await store.projection(compactor.leaf_entry_id)
        assert projection.compaction is not None
        assert projection.compaction.summary == "SUMMARY-1"
        assert [entry.payload["content"] for entry in projection.entries] == [padding("KEEP")]
        assert projection.compaction.first_kept_entry_id == projection.entries[0].id

    async def test_trigger_ignores_superseded_usage(self, store: StorageStore) -> None:
        """跨轮 usage 不累计：最近一次响应重新定基线后，更早的 usage 不再参与估算。"""
        llm = FakeLLM()
        counter = TokenCounter()
        compactor = make_compactor(llm, store, counter=counter, context_window=110_000)
        first = [user(padding("OLD-TASK"))]
        await compactor.persist_messages(first)
        counter.record(Usage(prompt_tokens=100_000, completion_tokens=10, total_tokens=100_010), first)
        second = [assistant(padding("OLD-WORK"))]
        await compactor.persist_messages(second)
        counter.record(Usage(prompt_tokens=1_000, completion_tokens=10, total_tokens=1_010), [*first, *second])
        third = [user(padding("KEEP"))]
        await compactor.persist_messages(third)

        update = await compactor.prepare_next_turn(next_turn_context([*first, *second, *third]))

        assert update is None
        assert (await store.projection(compactor.leaf_entry_id)).compaction is None
        assert llm.requests == []

    async def test_prompt_checkpoint_snapshots_system_prompt_and_tools(self, store: StorageStore) -> None:
        """compaction 记录携带压缩边界处的 system prompt 与工具快照（prompt checkpoint）。"""
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=1)
        system = {"role": "system", "content": "You are IntelliAgent."}
        tools = [{"type": "function", "function": {"name": "rec", "description": "d", "parameters": {}}}]
        request = RequestContext(turn=1, model="fake/model", messages=[system, user("task")], tools=tools)

        await compactor.prepare_request(request)

        assert request.messages == [system, user("task")]  # 未压缩时投影即全量记录

        llm.enqueue(*summary_response("S"))
        outcome = await compactor.compact()

        assert outcome is not None
        projection = await store.projection(compactor.leaf_entry_id)
        assert projection.compaction is not None
        assert projection.compaction.prompt_checkpoint == {
            "system_prompt": "You are IntelliAgent.",
            "tools": ["rec"],
            "model": "fake/model",
        }

    async def test_compact_returns_none_when_nothing_to_summarize(self, store: StorageStore) -> None:
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=100)
        await compactor.persist_messages([user(padding("KEEP"))])

        outcome = await compactor.compact()

        assert outcome is None
        assert llm.requests == []
        assert (await store.projection(compactor.leaf_entry_id)).compaction is None


class TestSummarization:
    """LLM 摘要：固定结构、增量更新、拒绝截断/工具调用、split turn 前缀单独总结。"""

    async def test_incremental_summary_carries_previous_summary(self, store: StorageStore) -> None:
        """第二次压缩走增量 update prompt，携带上次摘要而不是重写全史。"""
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=100)
        await compactor.persist_messages([user(padding("OLD")), assistant(padding("OLD")), user(padding("KEEP"))])
        llm.enqueue(*summary_response("SUMMARY-1"))
        outcome1 = await compactor.compact()
        assert outcome1 is not None and outcome1.summary == "SUMMARY-1"

        await compactor.persist_messages([assistant(padding("MORE")), user(padding("MORE"))])
        llm.enqueue(*summary_response("SUMMARY-2"))
        outcome2 = await compactor.compact()
        assert outcome2 is not None and outcome2.summary == "SUMMARY-2"

        first_prompt = llm.requests[0].messages[1]["content"]
        second_prompt = llm.requests[1].messages[1]["content"]
        assert UPDATE_SUMMARIZATION_PROMPT not in first_prompt
        assert "SUMMARY-1" not in first_prompt
        assert "SUMMARY-1" in second_prompt
        assert UPDATE_SUMMARIZATION_PROMPT in second_prompt
        assert llm.requests[1].messages[0] == {"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT}

    async def test_truncated_summary_is_rejected_and_retried(self, store: StorageStore) -> None:
        """被输出上限截断的摘要（stop=length）拒绝使用，重试得到完整摘要。"""
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=100)
        await compactor.persist_messages([user(padding("OLD")), assistant(padding("OLD")), user(padding("KEEP"))])
        llm.enqueue(*summary_response("TRUNCATED", stop="length"))
        llm.enqueue(*summary_response("SUMMARY-1"))

        outcome = await compactor.compact()

        assert outcome is not None and outcome.summary == "SUMMARY-1"
        assert len(llm.requests) == 2

    async def test_tool_calling_summary_is_rejected_and_retried(self, store: StorageStore) -> None:
        """摘要请求不应调用工具：调工具的响应拒绝使用，重试得到纯文本摘要。"""
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=100)
        await compactor.persist_messages([user(padding("OLD")), assistant(padding("OLD")), user(padding("KEEP"))])
        llm.enqueue(*tool_call_response("c1", "rec", '{"path": "a.txt"}'))
        llm.enqueue(*summary_response("SUMMARY-1"))

        outcome = await compactor.compact()

        assert outcome is not None and outcome.summary == "SUMMARY-1"
        assert len(llm.requests) == 2

    async def test_summary_retries_exhausted_raises_compaction_error(self, store: StorageStore) -> None:
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=100, max_summary_attempts=3)
        await compactor.persist_messages([user(padding("OLD")), assistant(padding("OLD")), user(padding("KEEP"))])
        for _ in range(3):
            llm.enqueue(*summary_response("TRUNCATED", stop="length"))

        with pytest.raises(CompactionError, match="summar"):
            await compactor.compact()

        assert len(llm.requests) == 3
        assert (await store.projection(compactor.leaf_entry_id)).compaction is None

    async def test_split_turn_prefix_summarized_separately(self, store: StorageStore) -> None:
        """split turn：完整 turn 走历史摘要，被切 turn 的前缀用独立 prompt 单独总结后合并。"""
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=50)
        await compactor.persist_messages(
            [user(padding("OLD")), assistant(padding("OLD")), user(padding("PREFIX")), assistant(padding("KEEP"))]
        )
        llm.enqueue(*summary_response("H1"))
        llm.enqueue(*summary_response("P1"))

        outcome = await compactor.compact()

        assert outcome is not None
        assert outcome.is_split_turn is True
        assert outcome.summary == f"H1\n\n---\n\n{SPLIT_TURN_MARKER}\n\nP1"
        projection = await store.projection(compactor.leaf_entry_id)
        assert projection.compaction is not None
        assert outcome.first_kept_entry_id == projection.entries[0].id
        assert [entry.payload["content"] for entry in projection.entries] == [padding("KEEP")]
        assert TURN_PREFIX_SUMMARIZATION_PROMPT not in llm.requests[0].messages[1]["content"]
        assert TURN_PREFIX_SUMMARIZATION_PROMPT in llm.requests[1].messages[1]["content"]

    async def test_split_turn_without_history_uses_no_prior_history(self, store: StorageStore) -> None:
        """首段历史即被切 turn：历史为空不再发摘要请求，直接"No prior history."。"""
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=50)
        await compactor.persist_messages([user(padding("PREFIX")), assistant(padding("KEEP"))])
        llm.enqueue(*summary_response("P1"))

        outcome = await compactor.compact()

        assert outcome is not None
        assert outcome.summary == f"No prior history.\n\n---\n\n{SPLIT_TURN_MARKER}\n\nP1"
        assert len(llm.requests) == 1


class TestProjectionRegression:
    """压缩后重启投影不含被压缩 entry（旧 P0 缺陷：压缩与持久化脱节、重启后历史全回）。"""

    async def test_projection_excludes_compacted_entries_after_restart(self, store: StorageStore) -> None:
        llm = FakeLLM()
        compactor = make_compactor(llm, store, keep_recent_tokens=100)
        await compactor.persist_messages(
            [user(padding("OLD-TASK")), assistant(padding("OLD-WORK")), user(padding("KEEP-RECENT"))]
        )
        llm.enqueue(*summary_response("SUMMARY-1"))
        outcome = await compactor.compact()
        assert outcome is not None

        restarted = make_compactor(llm, store, keep_recent_tokens=100, resume_entry_id=compactor.leaf_entry_id)
        projected = await restarted.projection_messages()

        assert projected == [summary_message("SUMMARY-1"), user(padding("KEEP-RECENT"))]
        # 原始记录永不删除：被压缩 entry 仍完整可查
        path = await store.branch_path(compactor.leaf_entry_id)
        assert len(path) == 4  # 2 条被压缩 message + 1 条保留 message + 1 条 compaction
        assert any(entry.payload.get("content") == padding("OLD-TASK") for entry in path)

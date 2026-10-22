"""Compactor 与 Engine 接线：turn 边界阈值触发（prepareNextTurn）+ 每请求现算投影（prepareRequest）。

覆盖 issue #59 的重启回归：压缩后重启，请求上下文只有摘要与最近消息，不含被压缩 entry。
"""

from __future__ import annotations

import json

from src.core.compaction import summary_message
from src.core.engine import Engine
from src.core.token_counting import TokenCounter, UsageRecordingClient
from src.llm.stream import LLMEvent, Usage
from src.plugins.storage import StorageStore
from tests.core.compaction_support import (
    assistant,
    make_compactor,
    padding,
    summary_response,
    text_response,
    tool_call_response,
    user,
)
from tests.core.engine_support import FakeLLM, build_engine, make_tool

BIG_USAGE = Usage(prompt_tokens=90_000, completion_tokens=5, total_tokens=90_005)
OVER_THRESHOLD_USAGE = Usage(prompt_tokens=94_000, completion_tokens=5, total_tokens=94_005)
SMALL_USAGE = Usage(prompt_tokens=500, completion_tokens=1, total_tokens=501)


async def drive_run_until_compaction(
    engine: Engine,
    llm: FakeLLM,
    *,
    big_task: str,
    more: str,
    extra_responses: tuple[tuple[LLMEvent, ...], ...] = (),
) -> None:
    """两个 turn 的脚本：工具 turn（usage 未超阈值）→ steer 注入 → 文本 turn（usage 超阈值触发压缩）。

    第三段响应是压缩摘要（FakeLLM 按入队顺序应答，摘要请求在 turn 边界发出）；
    extra_responses 排在摘要之后（压缩后的后续轮响应）。
    """
    llm.enqueue(
        *tool_call_response("c1", "rec", json.dumps({"path": "a.txt"}), usage=BIG_USAGE),
        on_start=lambda: engine.steer(more),
    )
    llm.enqueue(*text_response("done", usage=OVER_THRESHOLD_USAGE))
    llm.enqueue(*summary_response("S1"))
    for response in extra_responses:
        llm.enqueue(*response)
    result = await engine.run(big_task)
    assert result.outcome == "settled"


async def test_projection_keeps_seeded_system_prompt_out_of_storage(store: StorageStore) -> None:
    """system prompt 不落 message entry，但每次投影都作为 leading system message。"""
    compactor = make_compactor(FakeLLM(), store, system_prompt="SYSTEM-PROMPT")
    await compactor.sync_messages([user("hello")])

    projection = await compactor.projection_messages()

    assert projection[0] == {"role": "system", "content": "SYSTEM-PROMPT"}
    assert projection[1] == user("hello")
    _summary, kept = await store.chat_projection(compactor.leaf_entry_id)
    assert [message for _entry_id, message in kept] == [user("hello")]


async def test_prepare_request_projects_without_touching_engine_record(store: StorageStore) -> None:
    """prepareRequest 的请求视图即投影；引擎 Conversation 记录保持原样（append-only）。"""
    llm = FakeLLM()
    counter = TokenCounter()
    compactor = make_compactor(llm, store, counter=counter)
    engine = build_engine(UsageRecordingClient(llm, counter), turn_hooks=compactor.hooks())
    llm.enqueue(*text_response("done"))

    await engine.run("task")

    assert llm.requests[0].messages == [{"role": "user", "content": "task"}]
    assert engine.messages == ({"role": "user", "content": "task"}, {"role": "assistant", "content": "done"})


async def test_engine_compacts_at_turn_boundary_with_real_usage(store: StorageStore) -> None:
    """阈值到即在 turn 边界压缩：写 compaction 记录（含 prompt checkpoint），下一次请求即现算投影。"""
    llm = FakeLLM()
    counter = TokenCounter()
    compactor = make_compactor(llm, store, counter=counter, context_window=110_000, keep_recent_tokens=50)
    engine = build_engine(UsageRecordingClient(llm, counter), tools=[make_tool([])], turn_hooks=compactor.hooks())
    more = padding("MORE")
    engine.follow_up(padding("NEXT"))
    await drive_run_until_compaction(
        engine,
        llm,
        big_task=padding("OLD-TASK"),
        more=more,
        extra_responses=(text_response("continued", usage=SMALL_USAGE),),  # 压缩后 follow-up 轮
    )

    projection = await store.projection(compactor.leaf_entry_id)
    assert projection.compaction is not None
    assert projection.compaction.summary == "S1"
    assert projection.compaction.prompt_checkpoint == {"system_prompt": "", "tools": ["rec"], "model": "fake/model"}
    assert [entry.payload["content"] for entry in projection.entries] == [more, "done", padding("NEXT"), "continued"]
    # 压缩后下一次请求 = 现算投影：摘要 + 保留段 + 新消息，被压缩 entry 不进视图
    # requests 顺序：turn1、turn2、压缩摘要、follow-up 轮
    assert llm.requests[3].messages == [
        summary_message("S1"),
        user(more),
        assistant("done"),
        user(padding("NEXT")),
    ]


async def test_restart_after_compaction_sends_summary_and_recent_messages(store: StorageStore) -> None:
    """重启回归（旧 P0 缺陷）：压缩后重启，请求上下文只有摘要与最近消息。"""
    llm = FakeLLM()
    counter = TokenCounter()
    compactor = make_compactor(llm, store, counter=counter, context_window=110_000, keep_recent_tokens=50)
    engine = build_engine(UsageRecordingClient(llm, counter), tools=[make_tool([])], turn_hooks=compactor.hooks())
    more = padding("MORE")
    await drive_run_until_compaction(engine, llm, big_task=padding("OLD-TASK"), more=more)

    # 重启：新 counter / 新 Compactor / 新 Engine，续接同一存储分支
    llm2 = FakeLLM()
    counter2 = TokenCounter()
    compactor2 = make_compactor(llm2, store, counter=counter2, resume_entry_id=compactor.leaf_entry_id)
    engine2 = build_engine(UsageRecordingClient(llm2, counter2), turn_hooks=compactor2.hooks())
    llm2.enqueue(*text_response("continued"))

    await engine2.run("continue the task")

    assert llm2.requests[0].messages == [
        summary_message("S1"),
        user(more),
        assistant("done"),
        {"role": "user", "content": "continue the task"},
    ]
    assert all("OLD-TASK" not in str(message.get("content")) for message in llm2.requests[0].messages)

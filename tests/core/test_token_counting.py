"""token 计数：provider 真实 usage 基线 + 尾部估算（pi-engine-principles §4、issue #59）。

阈值触发的前提是 token 计数：优先用最近一次响应的真实 usage，请求间新增消息按 chars/4 估算，
绝不把跨轮 usage 累加（旧 ContextManager 的误触发根因）；基线失配（压缩重建投影）退回整体估算。
"""

from __future__ import annotations

from src.core.token_counting import TokenCounter, UsageRecordingClient, estimate_tokens
from src.llm.stream import StreamRequest, Usage
from tests.core.compaction_support import assistant, tool_call, user
from tests.core.engine_support import FakeLLM, text_events


def test_estimate_tokens_uses_chars_over_four_heuristic() -> None:
    """单条消息估算：正文 + tool_call 的 name/arguments 都计入 chars/4。"""
    assert estimate_tokens(user("abcd")) == 1
    assert estimate_tokens(user("abcde")) == 2
    assert estimate_tokens(assistant("", tool_calls=[tool_call("c1", "{}")])) == 2  # "rec" + "{}" = 5 chars


def test_estimate_uses_real_usage_plus_trailing_estimate() -> None:
    """基线是真实 usage（覆盖请求消息前缀），之后新增消息按 chars/4 估算。"""
    counter = TokenCounter()
    covered = [user("a" * 400)]  # 100 tokens
    counter.record(Usage(prompt_tokens=1000, completion_tokens=50, total_tokens=1050), covered)

    assert counter.estimate([*covered, user("b" * 8)]) == 1002  # 1000 + 2


def test_estimate_does_not_accumulate_across_turns() -> None:
    """跨轮只认最新 usage：新响应重新定基线，不把多轮 usage 相加。"""
    counter = TokenCounter()
    messages = [user("a" * 400), assistant("b" * 400)]
    counter.record(Usage(prompt_tokens=1000, completion_tokens=10, total_tokens=1010), messages[:1])
    counter.record(Usage(prompt_tokens=1200, completion_tokens=10, total_tokens=1210), messages)

    assert counter.estimate(messages) == 1200  # 不是 2200
    assert counter.estimate([*messages, user("c" * 8)]) == 1202


def test_estimate_falls_back_to_char_heuristic_without_usage() -> None:
    """无 usage（error/aborted 或 provider 不报）时整体按 chars/4 估算。"""
    counter = TokenCounter()
    counter.record(None, [user("a" * 400)])
    assert counter.estimate([user("a" * 400)]) == 100

    counter.record(Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0), [user("a" * 400)])
    assert counter.estimate([user("a" * 400), assistant("b" * 400)]) == 200


def test_estimate_rebaselines_when_baseline_diverges() -> None:
    """基线消息不再是当前列表前缀（如压缩重建投影）时退回整体估算。"""
    counter = TokenCounter()
    counter.record(Usage(prompt_tokens=1000, completion_tokens=10, total_tokens=1010), [user("a" * 400)])

    assert counter.estimate([user("z" * 400)]) == 100


def test_usage_recording_client_records_usage_and_passes_events_through() -> None:
    """装饰器原样透传事件，只在 Done 上把 usage 与请求前缀喂给 TokenCounter。"""
    inner = FakeLLM()
    events = text_events("hi")
    inner.enqueue(*events)
    counter = TokenCounter()
    client = UsageRecordingClient(inner, counter)

    streamed = list(client.stream(StreamRequest(model="fake/model", messages=[user("task")])))

    assert streamed == list(events)
    # text_events 的 usage.prompt_tokens=1，尾部 assistant("hi") 2 chars → +1
    assert counter.estimate([user("task"), assistant("hi")]) == 2

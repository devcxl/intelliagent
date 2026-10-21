"""编排层契约：与传输无关的重试、错误进流与 usage 账本（注入 fake adapter）。"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import pytest

from src.llm.client import ProviderClient
from src.llm.errors import ProviderError
from src.llm.stream import Done, Error, LLMEvent, StreamRequest, TextDelta, ToolCallDelta, Usage


class ScriptedAdapter:
    """按脚本产出事件或抛出异常；记录调用次数，不触网。"""

    def __init__(self, *episodes: list[LLMEvent] | BaseException) -> None:
        self.episodes = list(episodes)
        self.calls = 0

    def stream(
        self, request: StreamRequest, abort: threading.Event | None = None, *, timeout: float
    ) -> Iterator[LLMEvent]:
        self.calls += 1
        episode = self.episodes.pop(0)
        if isinstance(episode, BaseException):
            raise episode
        yield from episode


class SleepRecorder:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _request() -> StreamRequest:
    return StreamRequest(model="test/model", messages=[{"role": "user", "content": "hi"}])


def test_retryable_error_before_first_event_is_retried() -> None:
    """首个事件前的可重试错误按退避重试，重试成功后正常收束并落账 usage。"""
    adapter = ScriptedAdapter(
        ProviderError("TimeoutError: boom", retryable=True),
        [TextDelta("ok"), Done("stop", Usage(10, 5, 15))],
    )
    sleep = SleepRecorder()
    client = ProviderClient(adapter, sleep=sleep)

    events = list(client.stream(_request()))

    assert events == [TextDelta("ok"), Done("stop", Usage(10, 5, 15))]
    assert adapter.calls == 2
    assert sleep.sleeps == [1.0]
    assert client.usage_log == [Usage(10, 5, 15)]


def test_error_after_first_event_is_not_retried() -> None:
    """已产出增量后不重试，错误进流并以 error 收束。"""

    def partial_then_fail() -> Iterator[LLMEvent]:
        yield TextDelta("partial")
        raise ProviderError("ConnectionError: dropped", retryable=True)

    adapter = ScriptedAdapter(partial_then_fail())
    sleep = SleepRecorder()
    client = ProviderClient(adapter, sleep=sleep)

    events = list(client.stream(_request()))

    assert events == [TextDelta("partial"), Error("ConnectionError: dropped"), Done("error", None)]
    assert adapter.calls == 1
    assert sleep.sleeps == []


def test_non_retryable_error_fails_fast() -> None:
    adapter = ScriptedAdapter(ProviderError("BadRequestError: bad request", retryable=False))
    sleep = SleepRecorder()
    client = ProviderClient(adapter, sleep=sleep)

    events = list(client.stream(_request()))

    assert events == [Error("BadRequestError: bad request"), Done("error", None)]
    assert adapter.calls == 1
    assert sleep.sleeps == []


def test_programming_errors_are_not_swallowed() -> None:
    adapter = ScriptedAdapter(TypeError("simulated bug"))

    with pytest.raises(TypeError):
        list(ProviderClient(adapter).stream(_request()))


def test_abort_before_stream_does_not_call_adapter() -> None:
    adapter = ScriptedAdapter()
    abort = threading.Event()
    abort.set()

    events = list(ProviderClient(adapter).stream(_request(), abort=abort))

    assert events == [Done("aborted", None)]
    assert adapter.calls == 0


def test_seam_carries_tool_deltas_and_exactly_one_done() -> None:
    """适配器 seam 与协议无关：工具增量原样透传，单次流仍只有一个 Done。"""
    adapter = ScriptedAdapter(
        [
            ToolCallDelta(0, "call_1", "read", '{"pa'),
            ToolCallDelta(0, None, None, 'th": "x"}'),
            Done("stop", None),
        ]
    )

    events = list(ProviderClient(adapter).stream(_request()))

    assert events == [
        ToolCallDelta(0, "call_1", "read", '{"pa'),
        ToolCallDelta(0, None, None, 'th": "x"}'),
        Done("stop", None),
    ]
    assert sum(isinstance(event, Done) for event in events) == 1

"""流协议语义测试（录制传输）：事件序列、stopReason 分类、usage 逐响应落账、abort。"""

from __future__ import annotations

import threading

import pytest

from src.llm.client import ProviderClient
from src.llm.protocols.litellm_adapter import LitellmAdapter
from src.llm.stream import Done, Error, StreamRequest, TextDelta, ToolCallDelta, Usage
from tests.llm.recorded import (
    FAKE_MODEL,
    Recorder,
    finish_chunk,
    text_chunk,
    tool_chunk,
    usage,
    usage_only_chunk,
)


def _request() -> StreamRequest:
    return StreamRequest(model=FAKE_MODEL, messages=[{"role": "user", "content": "hi"}])


def test_event_sequence_matches_recorded_stream(recorder: Recorder, client: ProviderClient) -> None:
    recorder.record(
        [
            text_chunk("hel"),
            text_chunk("lo"),
            tool_chunk(index=0, id="call_1", name="get_weather", arguments='{"city":'),
            tool_chunk(index=0, arguments='"Paris"}'),
            finish_chunk("stop", usage(10, 5, 15)),
        ]
    )

    events = list(client.stream(_request()))

    assert events == [
        TextDelta("hel"),
        TextDelta("lo"),
        ToolCallDelta(0, "call_1", "get_weather", '{"city":'),
        ToolCallDelta(0, None, None, '"Paris"}'),
        Done("stop", Usage(10, 5, 15)),
    ]
    assert [event.kind for event in events] == ["text_delta", "text_delta", "toolcall_delta", "toolcall_delta", "done"]


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        ("stop", "stop"),
        ("tool_calls", "stop"),
        ("function_call", "stop"),
        (None, "length"),
        ("length", "length"),
        ("max_tokens", "length"),
        ("content_filter", "length"),
        ("tool_calls", "stop"),
    ],
)
def test_stop_reason_classification(
    recorder: Recorder, client: ProviderClient, finish_reason: str | None, expected: str
) -> None:
    recorder.record([text_chunk("x"), finish_chunk(finish_reason)])

    events = list(client.stream(_request()))

    assert isinstance(events[-1], Done)
    assert events[-1].stop_reason == expected


def test_usage_ledger_records_every_response(recorder: Recorder, client: ProviderClient) -> None:
    recorder.record([text_chunk("one"), finish_chunk("stop", usage(10, 5, 15))])
    recorder.record([text_chunk("two"), finish_chunk("stop", usage(7, 3, 10))])

    first = list(client.stream(_request()))
    second = list(client.stream(_request()))

    assert first[-1].usage == Usage(10, 5, 15)
    assert second[-1].usage == Usage(7, 3, 10)
    assert client.usage_log == [Usage(10, 5, 15), Usage(7, 3, 10)]


def test_usage_only_chunk_is_collected(recorder: Recorder, client: ProviderClient) -> None:
    recorder.record([text_chunk("hi"), finish_chunk("stop"), usage_only_chunk(usage(10, 5, 15))])

    events = list(client.stream(_request()))

    assert events[-1] == Done("stop", Usage(10, 5, 15))


def test_request_fields_pass_through_to_litellm(recorder: Recorder, client: ProviderClient) -> None:
    tools = [{"type": "function", "function": {"name": "get_weather"}}]
    recorder.record([finish_chunk("stop", usage(1, 1, 2))])
    request = StreamRequest(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": "hi"}],
        tools=tools,
        temperature=0.2,
        max_tokens=64,
    )

    list(client.stream(request))

    call = recorder.calls[0]
    assert call["model"] == "deepseek/deepseek-chat"
    assert call["messages"] == [{"role": "user", "content": "hi"}]
    assert call["tools"] == tools
    assert call["temperature"] == 0.2
    assert call["max_tokens"] == 64
    assert call["stream"] is True
    assert call["stream_options"] == {"include_usage": True}


def test_tools_request_skips_litellm_mcp_gateway(recorder: Recorder, client: ProviderClient) -> None:
    """tools 非空时跳过 litellm 的 MCP 网关导入：该分支要求 mcp>=2.2，本项目锁 mcp 1.x。

    回归：缺该参数时 litellm 在发出请求前就 ImportError（CacheableResult），工具调用全不可用。
    """
    recorder.record([finish_chunk("stop")])
    tools = [{"type": "function", "function": {"name": "read"}}]

    list(client.stream(StreamRequest(model=FAKE_MODEL, messages=[{"role": "user", "content": "hi"}], tools=tools)))

    assert recorder.calls[0]["_skip_mcp_handler"] is True


def test_abort_before_stream_ends_with_aborted(recorder: Recorder, client: ProviderClient) -> None:
    abort = threading.Event()
    abort.set()

    events = list(client.stream(_request(), abort=abort))

    assert events == [Done("aborted", None)]
    assert recorder.calls == []


def test_abort_mid_stream_ends_with_aborted(recorder: Recorder, client: ProviderClient) -> None:
    recorder.record([text_chunk("one"), text_chunk("two"), text_chunk("three"), finish_chunk("stop", usage(1, 1, 2))])
    abort = threading.Event()
    stream = client.stream(_request(), abort=abort)

    assert next(stream) == TextDelta("one")
    abort.set()

    assert list(stream) == [Done("aborted", None)]
    assert client.usage_log == []


class TestReviewRegressions:
    """PR #68 审查回归：双 Done 防护、未知 finish_reason 截断化、abort usage 落账、编程错误 rethrow。"""

    def test_stream_close_failure_after_done_does_not_emit_second_done(self, recorder: Recorder) -> None:
        """close() 在 Done 产出后抛异常不得二次产出事件（恰好一个 Done 协议）。"""

        class ClosePoisonStream:
            def __init__(self, chunks: list[object]) -> None:
                self._it = iter(chunks)

            def __iter__(self) -> object:
                return self

            def __next__(self) -> object:
                return next(self._it)

            def close(self) -> None:
                raise RuntimeError("close failed")

        chunks = [text_chunk("hi"), finish_chunk("stop", usage(1, 1, 2))]
        recorder.record(ClosePoisonStream(chunks))
        client = ProviderClient(LitellmAdapter(), sleep=recorder.sleep)
        events = list(client.stream(_request()))
        assert sum(isinstance(e, Done) for e in events) == 1
        assert not any(isinstance(e, Error) for e in events)

    def test_unknown_finish_reason_maps_to_length_not_stop(self, recorder: Recorder, client: ProviderClient) -> None:
        """content_filter 等未知 finish_reason 携带残缺 tool call，必须归 length（US22）。"""
        recorder.record(
            [tool_chunk(index=0, id="c1", name="f", arguments='{"a": '), finish_chunk("content_filter", None)]
        )
        events = list(client.stream(_request()))
        done = [e for e in events if isinstance(e, Done)][-1]
        assert done.stop_reason == "length"

    def test_abort_accounts_partial_usage(self, recorder: Recorder) -> None:
        """abort 时已消耗 token 随 Done 携带并落账（pi 纪律：usage 逐响应落账）。"""
        abort = threading.Event()

        def episode() -> object:
            yield usage_only_chunk(usage(10, 5, 15))  # 先落一笔 usage
            abort.set()  # 在消费下一个 chunk 前置位，边界处触发 abort
            yield text_chunk("more")

        recorder.record(episode())
        client = ProviderClient(LitellmAdapter(), sleep=recorder.sleep)
        events = list(client.stream(_request(), abort=abort))
        done = [e for e in events if isinstance(e, Done)][-1]
        assert done.stop_reason == "aborted"
        assert done.usage is not None  # 已消耗的 token 不丢账
        assert client.usage_log == [done.usage]

    def test_programming_errors_are_not_swallowed_into_stream(self, recorder: Recorder, client: ProviderClient) -> None:
        """TypeError 等编程错误必须 rethrow，不得伪装成模型错误进流。"""

        class BrokenStream:
            def __iter__(self) -> object:
                raise TypeError("simulated bug")

        recorder.record(BrokenStream())
        with pytest.raises(TypeError):
            list(client.stream(_request()))

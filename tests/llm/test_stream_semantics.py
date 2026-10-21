"""流协议语义测试（录制传输）：事件序列、stopReason 分类、usage 逐响应落账、abort。"""

from __future__ import annotations

import threading

import pytest

from src.llm.litellm_client import LiteLLMClient
from src.llm.stream import Done, StreamRequest, TextDelta, ToolCallDelta, Usage
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


def test_event_sequence_matches_recorded_stream(recorder: Recorder, client: LiteLLMClient) -> None:
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
        (None, "stop"),
        ("length", "length"),
        ("max_tokens", "length"),
    ],
)
def test_stop_reason_classification(
    recorder: Recorder, client: LiteLLMClient, finish_reason: str | None, expected: str
) -> None:
    recorder.record([text_chunk("x"), finish_chunk(finish_reason)])

    events = list(client.stream(_request()))

    assert isinstance(events[-1], Done)
    assert events[-1].stop_reason == expected


def test_usage_ledger_records_every_response(recorder: Recorder, client: LiteLLMClient) -> None:
    recorder.record([text_chunk("one"), finish_chunk("stop", usage(10, 5, 15))])
    recorder.record([text_chunk("two"), finish_chunk("stop", usage(7, 3, 10))])

    first = list(client.stream(_request()))
    second = list(client.stream(_request()))

    assert first[-1].usage == Usage(10, 5, 15)
    assert second[-1].usage == Usage(7, 3, 10)
    assert client.usage_log == [Usage(10, 5, 15), Usage(7, 3, 10)]


def test_usage_only_chunk_is_collected(recorder: Recorder, client: LiteLLMClient) -> None:
    recorder.record([text_chunk("hi"), finish_chunk("stop"), usage_only_chunk(usage(10, 5, 15))])

    events = list(client.stream(_request()))

    assert events[-1] == Done("stop", Usage(10, 5, 15))


def test_request_fields_pass_through_to_litellm(recorder: Recorder, client: LiteLLMClient) -> None:
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


def test_abort_before_stream_ends_with_aborted(recorder: Recorder, client: LiteLLMClient) -> None:
    abort = threading.Event()
    abort.set()

    events = list(client.stream(_request(), abort=abort))

    assert events == [Done("aborted", None)]
    assert recorder.calls == []


def test_abort_mid_stream_ends_with_aborted(recorder: Recorder, client: LiteLLMClient) -> None:
    recorder.record([text_chunk("one"), text_chunk("two"), text_chunk("three"), finish_chunk("stop", usage(1, 1, 2))])
    abort = threading.Event()
    stream = client.stream(_request(), abort=abort)

    assert next(stream) == TextDelta("one")
    abort.set()

    assert list(stream) == [Done("aborted", None)]
    assert client.usage_log == []

"""Anthropic Messages 适配器契约：消息投影、流事件、usage、停止原因与错误分类（fake SDK）。"""

from __future__ import annotations

import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from src.llm.errors import ProviderError
from src.llm.protocols.anthropic_messages import AnthropicMessagesAdapter
from src.llm.provider_registry import ModelTarget
from src.llm.stream import Done, StreamRequest, TextDelta, ToolCallDelta, Usage

TARGET = ModelTarget(
    provider="anthropic",
    model_id="claude",
    wire_model="claude-test",
    protocol="anthropic",
    api_base="https://api.anthropic.com",
    api_key="test-key",
    supports_tools=True,
    max_output_tokens=128,
    context_window=200000,
)


def _event(event_type: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=event_type, **fields)


def _message_start(input_tokens: int = 10, output_tokens: int = 1) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return _event("message_start", message=SimpleNamespace(usage=usage))


def _text_start(index: int = 0) -> SimpleNamespace:
    return _event("content_block_start", index=index, content_block=SimpleNamespace(type="text", text=""))


def _text_delta(text: str, index: int = 0) -> SimpleNamespace:
    return _event(
        "content_block_delta",
        index=index,
        delta=SimpleNamespace(type="text_delta", text=text),
    )


def _tool_start(index: int, tool_id: str, name: str) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", id=tool_id, name=name)
    return _event("content_block_start", index=index, content_block=block)


def _json_delta(index: int, partial: str) -> SimpleNamespace:
    return _event(
        "content_block_delta",
        index=index,
        delta=SimpleNamespace(type="input_json_delta", partial_json=partial),
    )


def _message_delta(stop_reason: str | None, output_tokens: int = 5) -> SimpleNamespace:
    usage = SimpleNamespace(output_tokens=output_tokens)
    return _event("message_delta", delta=SimpleNamespace(stop_reason=stop_reason), usage=usage)


class FakeStream:
    def __init__(self, events: list[Any], close_error: Exception | None = None) -> None:
        self._events = events
        self.close_error = close_error
        self.closed = False

    def __iter__(self) -> Any:
        return iter(self._events)

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class FakeMessages:
    def __init__(self, stream: FakeStream | None = None, error: Exception | None = None) -> None:
        self.stream = stream
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.stream is not None
        return self.stream


class FakeClient:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages = messages
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _factory(client: FakeClient, calls: list[tuple[ModelTarget, float]]) -> Any:
    def build(target: ModelTarget, timeout: float) -> FakeClient:
        calls.append((target, timeout))
        return client

    return build


def _request(**overrides: Any) -> StreamRequest:
    values: dict[str, Any] = {"model": "anthropic/claude", "messages": [{"role": "user", "content": "hi"}]}
    values.update(overrides)
    return StreamRequest(**values)


def test_streams_text_and_usage() -> None:
    stream = FakeStream([_message_start(), _text_start(), _text_delta("Hello"), _message_delta("end_turn", 4)])
    adapter = AnthropicMessagesAdapter(_factory(FakeClient(FakeMessages(stream)), []))

    events = list(adapter.stream(TARGET, _request(), timeout=60))

    assert events == [TextDelta("Hello"), Done("stop", Usage(10, 4, 14))]


def test_streams_tool_use_with_json_fragments() -> None:
    stream = FakeStream(
        [
            _message_start(),
            _tool_start(0, "toolu_1", "read"),
            _json_delta(0, '{"pa'),
            _json_delta(0, 'th": "a"}'),
            _message_delta("tool_use"),
        ]
    )
    adapter = AnthropicMessagesAdapter(_factory(FakeClient(FakeMessages(stream)), []))

    events = list(adapter.stream(TARGET, _request(), timeout=60))

    assert events == [
        ToolCallDelta(0, "toolu_1", "read", ""),
        ToolCallDelta(0, "toolu_1", "read", '{"pa'),
        ToolCallDelta(0, "toolu_1", "read", 'th": "a"}'),
        Done("stop", Usage(10, 5, 15)),
    ]


def test_projects_system_tools_and_tool_results() -> None:
    messages = FakeMessages(FakeStream([_message_start(), _message_delta("end_turn", 1)]))
    adapter = AnthropicMessagesAdapter(_factory(FakeClient(messages), []))
    request = _request(
        messages=[
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "read", "arguments": '{"path": "a"}'}}
                ],
            },
            {"role": "tool", "tool_call_id": "c1", "content": "result"},
            {"role": "tool", "tool_call_id": "c2", "content": "result2"},
        ],
        tools=[
            {"type": "function", "function": {"name": "read", "description": "d", "parameters": {"type": "object"}}}
        ],
    )

    list(adapter.stream(TARGET, request, timeout=60))

    kwargs = messages.calls[0]
    assert kwargs["system"] == "sys"
    assert kwargs["max_tokens"] == 128
    assert kwargs["tools"] == [{"name": "read", "description": "d", "input_schema": {"type": "object"}}]
    assert kwargs["messages"][1] == {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": "c1", "name": "read", "input": {"path": "a"}}],
    }
    assert kwargs["messages"][2]["role"] == "user"
    assert kwargs["messages"][2]["content"] == [
        {"type": "tool_result", "tool_use_id": "c1", "content": "result"},
        {"type": "tool_result", "tool_use_id": "c2", "content": "result2"},
    ]


def test_request_max_tokens_wins_and_default_when_absent() -> None:
    messages = FakeMessages(FakeStream([_message_start(), _message_delta("end_turn", 1)]))
    adapter = AnthropicMessagesAdapter(_factory(FakeClient(messages), []))
    list(adapter.stream(TARGET, _request(max_tokens=7), timeout=60))
    assert messages.calls[0]["max_tokens"] == 7

    no_limit = replace(TARGET, max_output_tokens=None)
    messages2 = FakeMessages(FakeStream([_message_start(), _message_delta("end_turn", 1)]))
    adapter2 = AnthropicMessagesAdapter(_factory(FakeClient(messages2), []))
    list(adapter2.stream(no_limit, _request(), timeout=60))
    assert messages2.calls[0]["max_tokens"] == 4096


def test_abort_mid_stream() -> None:
    stream = FakeStream([_message_start(), _text_start(), _text_delta("one"), _text_delta("two")])
    adapter = AnthropicMessagesAdapter(_factory(FakeClient(FakeMessages(stream)), []))
    abort = threading.Event()
    events = adapter.stream(TARGET, _request(), abort, timeout=60)

    assert next(events) == TextDelta("one")
    abort.set()
    assert list(events) == [Done("aborted", Usage(10, 1, 11))]
    assert stream.closed is True


def test_stop_reason_classification() -> None:
    for reason, expected in [
        ("end_turn", "stop"),
        ("tool_use", "stop"),
        ("stop_sequence", "stop"),
        ("refusal", "stop"),
        ("max_tokens", "length"),
        ("pause_turn", "length"),
        (None, "length"),
    ]:
        stream = FakeStream([_message_start(), _message_delta(reason)])
        adapter = AnthropicMessagesAdapter(_factory(FakeClient(FakeMessages(stream)), []))
        events = list(adapter.stream(TARGET, _request(), timeout=60))
        assert events[-1] == Done(expected, Usage(10, 5, 15))


def test_error_event_is_retryable_provider_error() -> None:
    stream = FakeStream([_event("error", error=SimpleNamespace(type="overloaded_error", message="busy"))])
    adapter = AnthropicMessagesAdapter(_factory(FakeClient(FakeMessages(stream)), []))

    with pytest.raises(ProviderError) as excinfo:
        list(adapter.stream(TARGET, _request(), timeout=60))
    assert excinfo.value.retryable is True
    assert "overloaded_error" in str(excinfo.value)

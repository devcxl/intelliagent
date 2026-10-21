"""OpenAI Responses 适配器契约：input 投影、流事件、usage、停止原因与错误分类（fake SDK）。"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest

from src.llm.errors import ProviderError
from src.llm.protocols.openai_responses import OpenAIResponsesAdapter
from src.llm.provider_registry import ModelTarget
from src.llm.stream import Done, StreamRequest, TextDelta, ToolCallDelta, Usage

TARGET = ModelTarget(
    provider="openai",
    model_id="gpt",
    wire_model="gpt-test",
    protocol="openai",
    api_base="https://api.openai.com/v1",
    api_key="test-key",
    supports_tools=True,
    max_output_tokens=256,
    context_window=128000,
)


def _event(event_type: str, **fields: Any) -> SimpleNamespace:
    return SimpleNamespace(type=event_type, **fields)


def _usage(prompt: int, completion: int, total: int) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=prompt, output_tokens=completion, total_tokens=total)


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


class FakeResponses:
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
    def __init__(self, responses: FakeResponses) -> None:
        self.responses = responses
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _factory(client: FakeClient, calls: list[tuple[ModelTarget, float]]) -> Any:
    def build(target: ModelTarget, timeout: float) -> FakeClient:
        calls.append((target, timeout))
        return client

    return build


def _request(**overrides: Any) -> StreamRequest:
    values: dict[str, Any] = {"model": "openai/gpt", "messages": [{"role": "user", "content": "hi"}]}
    values.update(overrides)
    return StreamRequest(**values)


def test_streams_text_and_usage() -> None:
    stream = FakeStream(
        [
            _event("response.output_text.delta", delta="Hel"),
            _event("response.output_text.delta", delta="lo"),
            _event("response.completed", response=SimpleNamespace(status="completed", usage=_usage(10, 5, 15))),
        ]
    )
    adapter = OpenAIResponsesAdapter(_factory(FakeClient(FakeResponses(stream)), []))

    events = list(adapter.stream(TARGET, _request(), timeout=60))

    assert events == [TextDelta("Hel"), TextDelta("lo"), Done("stop", Usage(10, 5, 15))]


def test_streams_function_call_arguments() -> None:
    stream = FakeStream(
        [
            _event(
                "response.output_item.added",
                output_index=1,
                item=SimpleNamespace(type="function_call", id="item_1", call_id="call_1", name="read"),
            ),
            _event("response.function_call_arguments.delta", item_id="item_1", output_index=1, delta='{"pa'),
            _event("response.function_call_arguments.delta", item_id="item_1", output_index=1, delta='th": "a"}'),
            _event("response.completed", response=SimpleNamespace(status="completed", usage=None)),
        ]
    )
    adapter = OpenAIResponsesAdapter(_factory(FakeClient(FakeResponses(stream)), []))

    events = list(adapter.stream(TARGET, _request(), timeout=60))

    assert events == [
        ToolCallDelta(1, "call_1", "read", ""),
        ToolCallDelta(1, "call_1", "read", '{"pa'),
        ToolCallDelta(1, "call_1", "read", 'th": "a"}'),
        Done("stop", None),
    ]


def test_projects_system_tools_and_history() -> None:
    responses = FakeResponses(
        FakeStream([_event("response.completed", response=SimpleNamespace(status="completed", usage=None))])
    )
    adapter = OpenAIResponsesAdapter(_factory(FakeClient(responses), []))
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
        ],
        tools=[
            {"type": "function", "function": {"name": "read", "description": "d", "parameters": {"type": "object"}}}
        ],
    )

    list(adapter.stream(TARGET, request, timeout=60))

    kwargs = responses.calls[0]
    assert kwargs["instructions"] == "sys"
    assert kwargs["max_output_tokens"] == 256
    assert kwargs["tools"] == [
        {"type": "function", "name": "read", "description": "d", "parameters": {"type": "object"}}
    ]
    assert kwargs["input"] == [
        {"role": "user", "content": "hi"},
        {"type": "function_call", "call_id": "c1", "name": "read", "arguments": '{"path": "a"}'},
        {"type": "function_call_output", "call_id": "c1", "output": "result"},
    ]


def test_stop_reason_classification() -> None:
    for status, expected in [("completed", "stop"), ("incomplete", "length"), (None, "length")]:
        stream = FakeStream([_event("response.completed", response=SimpleNamespace(status=status, usage=None))])
        adapter = OpenAIResponsesAdapter(_factory(FakeClient(FakeResponses(stream)), []))
        events = list(adapter.stream(TARGET, _request(), timeout=60))
        assert events[-1] == Done(expected, None)


def test_abort_mid_stream() -> None:
    stream = FakeStream(
        [
            _event("response.output_text.delta", delta="one"),
            _event("response.output_text.delta", delta="two"),
            _event("response.completed", response=SimpleNamespace(status="completed", usage=None)),
        ]
    )
    adapter = OpenAIResponsesAdapter(_factory(FakeClient(FakeResponses(stream)), []))
    abort = threading.Event()
    events = adapter.stream(TARGET, _request(), abort, timeout=60)

    assert next(events) == TextDelta("one")
    abort.set()
    assert list(events) == [Done("aborted", None)]
    assert stream.closed is True


def test_failed_event_is_provider_error() -> None:
    stream = FakeStream([_event("response.failed", error=SimpleNamespace(message="bad response"))])
    adapter = OpenAIResponsesAdapter(_factory(FakeClient(FakeResponses(stream)), []))

    with pytest.raises(ProviderError, match="bad response"):
        list(adapter.stream(TARGET, _request(), timeout=60))

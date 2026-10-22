"""OpenAI Chat Completions 适配器契约：请求投影、流事件翻译、abort 与错误分类（fake SDK）。"""

from __future__ import annotations

import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

from src.llm.errors import ProviderError
from src.llm.protocols.openai_chat import OpenAIChatAdapter
from src.llm.provider_registry import ModelTarget
from src.llm.stream import Done, StreamRequest, TextDelta, ToolCallDelta, Usage

TARGET = ModelTarget(
    provider="local",
    model_id="model",
    wire_model="wire-model",
    protocol="openai-compatible",
    api_base="http://127.0.0.1:9/v1",
    api_key="test-key",
    supports_tools=True,
    max_output_tokens=128,
    context_window=4096,
)


def _usage(prompt: int, completion: int, total: int) -> SimpleNamespace:
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


def _text_chunk(text: str, finish_reason: str | None = None, usage: Any = None) -> SimpleNamespace:
    delta = SimpleNamespace(content=text, tool_calls=[])
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)], usage=usage)


def _tool_chunk(index: int, tool_id: str | None, name: str | None, arguments: str) -> SimpleNamespace:
    function = SimpleNamespace(name=name, arguments=arguments)
    delta = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(index=index, id=tool_id, function=function)])
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=None)], usage=None)


class FakeStream:
    """可迭代的 SDK 流；记录是否关闭。"""

    def __init__(self, chunks: list[Any], close_error: Exception | None = None) -> None:
        self._chunks = chunks
        self.close_error = close_error
        self.closed = False

    def __iter__(self) -> Any:
        return iter(self._chunks)

    def close(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class FakeCompletions:
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
    def __init__(self, completions: FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _client_factory(client: FakeClient, calls: list[tuple[ModelTarget, float]]) -> Any:
    def factory(target: ModelTarget, timeout: float) -> FakeClient:
        calls.append((target, timeout))
        return client

    return factory


def _request(**overrides: Any) -> StreamRequest:
    values: dict[str, Any] = {"model": "local/model", "messages": [{"role": "user", "content": "hi"}]}
    values.update(overrides)
    return StreamRequest(**values)


def test_streams_text_and_usage_and_closes_client() -> None:
    usage = _usage(10, 5, 15)
    completions = FakeCompletions(FakeStream([_text_chunk("hel"), _text_chunk("lo", "stop", usage)]))
    client = FakeClient(completions)
    calls: list[tuple[ModelTarget, float]] = []
    adapter = OpenAIChatAdapter(_client_factory(client, calls))

    events = list(adapter.stream(TARGET, _request(), timeout=12.5))

    assert events == [TextDelta("hel"), TextDelta("lo"), Done("stop", Usage(10, 5, 15))]
    assert calls == [(TARGET, 12.5)]
    assert client.chat.completions.calls[0]["model"] == "wire-model"
    assert client.closed is True


def test_maps_fragmented_tool_calls() -> None:
    completions = FakeCompletions(
        FakeStream(
            [
                _tool_chunk(0, "call_1", "read", '{"pa'),
                _tool_chunk(0, None, None, 'th": "x"}'),
                _text_chunk("", "tool_calls"),
            ]
        )
    )
    adapter = OpenAIChatAdapter(_client_factory(FakeClient(completions), []))

    events = list(adapter.stream(TARGET, _request(), timeout=60))

    assert events == [
        ToolCallDelta(0, "call_1", "read", '{"pa'),
        ToolCallDelta(0, None, None, 'th": "x"}'),
        Done("stop", None),
    ]


def test_request_projection_uses_limits_and_tool_gate() -> None:
    completions = FakeCompletions(FakeStream([_text_chunk("ok", "stop")]))
    adapter = OpenAIChatAdapter(_client_factory(FakeClient(completions), []))
    tools = [{"type": "function", "function": {"name": "read"}}]

    list(adapter.stream(TARGET, _request(tools=tools, temperature=0.2), timeout=60))

    kwargs = completions.calls[0]
    assert kwargs["tools"] == tools
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 128
    assert kwargs["stream"] is True
    assert kwargs["stream_options"] == {"include_usage": True}

    no_tools_target = replace(TARGET, supports_tools=False)
    completions2 = FakeCompletions(FakeStream([_text_chunk("ok", "stop")]))
    adapter2 = OpenAIChatAdapter(_client_factory(FakeClient(completions2), []))
    list(adapter2.stream(no_tools_target, _request(tools=tools, max_tokens=7), timeout=60))
    assert "tools" not in completions2.calls[0]
    assert completions2.calls[0]["max_tokens"] == 7


def test_multiple_system_messages_fold_to_single_leading_system() -> None:
    completions = FakeCompletions(FakeStream([_text_chunk("ok", "stop")]))
    adapter = OpenAIChatAdapter(_client_factory(FakeClient(completions), []))
    messages = [
        {"role": "system", "content": "preamble"},
        {"role": "system", "content": "<available_skills/>"},
        {"role": "user", "content": "hi"},
    ]

    list(adapter.stream(TARGET, _request(messages=messages), timeout=60))

    projected = completions.calls[0]["messages"]
    assert projected[0] == {"role": "system", "content": "preamble\n\n<available_skills/>"}
    assert projected[1] == {"role": "user", "content": "hi"}


def test_abort_mid_stream_ends_with_aborted_and_closes() -> None:
    stream = FakeStream([_text_chunk("one"), _text_chunk("two", "stop")])
    adapter = OpenAIChatAdapter(_client_factory(FakeClient(FakeCompletions(stream)), []))
    abort = threading.Event()
    events = adapter.stream(TARGET, _request(), abort, timeout=60)

    assert next(events) == TextDelta("one")
    abort.set()
    assert list(events) == [Done("aborted", None)]
    assert stream.closed is True


def test_stop_reason_classification() -> None:
    for finish, expected in [
        ("stop", "stop"),
        ("tool_calls", "stop"),
        ("length", "length"),
        ("content_filter", "length"),
    ]:
        completions = FakeCompletions(FakeStream([_text_chunk("x", finish)]))
        adapter = OpenAIChatAdapter(_client_factory(FakeClient(completions), []))
        events = list(adapter.stream(TARGET, _request(), timeout=60))
        assert events[-1] == Done(expected, None)


def test_call_errors_map_to_provider_error_and_programming_errors_propagate() -> None:
    completions = FakeCompletions(error=ConnectionError("dropped"))
    adapter = OpenAIChatAdapter(_client_factory(FakeClient(completions), []))

    with pytest.raises(ProviderError) as excinfo:
        list(adapter.stream(TARGET, _request(), timeout=60))
    assert str(excinfo.value) == "ConnectionError: dropped"
    assert excinfo.value.retryable is True

    completions = FakeCompletions(error=TypeError("bug"))
    adapter = OpenAIChatAdapter(_client_factory(FakeClient(completions), []))
    with pytest.raises(TypeError):
        list(adapter.stream(TARGET, _request(), timeout=60))


def test_close_failure_after_done_does_not_emit_second_done() -> None:
    stream = FakeStream([_text_chunk("hi", "stop")], close_error=ConnectionError("close failed"))
    adapter = OpenAIChatAdapter(_client_factory(FakeClient(FakeCompletions(stream)), []))

    events = list(adapter.stream(TARGET, _request(), timeout=60))

    assert events == [TextDelta("hi"), Done("stop", None)]

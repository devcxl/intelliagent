"""统一流协议契约测试：fake（录制传输）与真实 litellm 双路径共用同一测试组。

每条流的事件词汇只允许 text_delta / toolcall_delta / done / error；每条流以恰好一个 Done 收尾。
"""

from __future__ import annotations

from src.llm.stream import Done, LLMEvent, TextDelta, ToolCallDelta
from tests.llm.backends import Backend
from tests.llm.recorded import EXPECTED_TEXT, EXPECTED_TOOL_NAME


def _text_of(events: list[LLMEvent]) -> str:
    return "".join(event.text for event in events if isinstance(event, TextDelta))


def test_text_stream_events(backend: Backend) -> None:
    events = list(backend.client.stream(backend.text_request()))

    assert events
    done = events[-1]
    assert isinstance(done, Done)
    assert done.stop_reason == "stop"
    assert all(isinstance(event, (TextDelta, ToolCallDelta)) for event in events[:-1])
    text_events = [event for event in events if isinstance(event, TextDelta)]
    assert text_events
    assert EXPECTED_TEXT in _text_of(events).lower()


def test_tool_call_delta_events(backend: Backend) -> None:
    events = list(backend.client.stream(backend.tool_request()))

    assert isinstance(events[-1], Done)
    tool_events = [event for event in events if isinstance(event, ToolCallDelta)]
    assert tool_events
    assert all(event.index >= 0 for event in tool_events)
    assert all(event.id or event.name or event.arguments_delta for event in tool_events)
    names = "".join(event.name for event in tool_events if event.name)
    assert EXPECTED_TOOL_NAME in names


def test_usage_recorded_per_response(backend: Backend) -> None:
    events = list(backend.client.stream(backend.text_request()))

    done = events[-1]
    assert isinstance(done, Done)
    assert done.usage is not None
    assert done.usage.prompt_tokens > 0
    assert done.usage.total_tokens > 0
    assert backend.client.usage_log == [done.usage]


def test_stop_reason_length(backend: Backend) -> None:
    events = list(backend.client.stream(backend.length_request()))

    assert isinstance(events[-1], Done)
    assert events[-1].stop_reason == "length"

"""事件模型协议测试：事件是协议而非日志（ADR 0010、pi-engine-principles §2）。

覆盖 message_* 事件族携带流式增量、tool_execution_* 事件族的形状，以及 LLM 流到 message 事件的适配。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.core.agent_events import (
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionStart,
    ToolExecutionUpdate,
    message_events,
)
from src.llm.stream import Done, Error, TextDelta, ToolCallDelta, Usage


class TestMessageEvents:
    """message_start/update/end：message_update 携带流式增量，MessageEnd 携带终止原因。"""

    def test_message_update_carries_text_deltas(self) -> None:
        stream = [TextDelta(text="你"), TextDelta(text="好"), Done(stop_reason="stop", usage=None)]

        events = list(message_events("m1", stream))

        assert isinstance(events[0], MessageStart)
        assert events[0].message_id == "m1"
        updates = [event for event in events if isinstance(event, MessageUpdate)]
        assert [update.delta for update in updates] == [TextDelta(text="你"), TextDelta(text="好")]
        assert all(update.message_id == "m1" for update in updates)
        assert isinstance(events[-1], MessageEnd)
        assert events[-1].stop_reason == "stop"

    def test_message_update_carries_toolcall_deltas(self) -> None:
        stream = [
            ToolCallDelta(index=0, id="c1", name="read", arguments_delta='{"path"'),
            ToolCallDelta(index=0, id=None, name=None, arguments_delta=': "a.txt"}'),
            Done(stop_reason="stop", usage=Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3)),
        ]

        events = list(message_events("m2", stream))

        updates = [event.delta for event in events if isinstance(event, MessageUpdate)]
        assert isinstance(updates[0], ToolCallDelta)
        assert updates[0].name == "read"
        assert updates[0].arguments_delta == '{"path"'
        assert updates[1].arguments_delta == ': "a.txt"}'

    def test_error_delta_passes_through_then_end_carries_error_stop_reason(self) -> None:
        stream = [Error(message="boom"), Done(stop_reason="error", usage=None)]

        events = list(message_events("m3", stream))

        assert isinstance(events[1], MessageUpdate)
        assert isinstance(events[1].delta, Error)
        assert events[1].delta.message == "boom"
        assert events[-1] == MessageEnd(message_id="m3", stop_reason="error")

    def test_length_stop_reason_reaches_message_end(self) -> None:
        events = list(message_events("m4", [Done(stop_reason="length", usage=None)]))

        assert events[-1] == MessageEnd(message_id="m4", stop_reason="length")

    def test_done_usage_reaches_message_end(self) -> None:
        usage = Usage(prompt_tokens=11, completion_tokens=7, total_tokens=18)

        events = list(message_events("m8", [TextDelta(text="hi"), Done(stop_reason="stop", usage=usage)]))

        assert events[-1] == MessageEnd(message_id="m8", stop_reason="stop", usage=usage)

    def test_missing_usage_stays_none_on_error_and_aborted(self) -> None:
        for stop_reason in ("error", "aborted"):
            events = list(message_events(f"m-{stop_reason}", [Done(stop_reason=stop_reason, usage=None)]))

            assert events[-1].usage is None

    def test_stream_without_done_is_a_contract_violation(self) -> None:
        with pytest.raises(ValueError, match="without Done"):
            list(message_events("m5", [TextDelta(text="x")]))

    def test_role_defaults_to_assistant_and_is_overridable(self) -> None:
        stream = [Done(stop_reason="stop", usage=None)]

        default_role = list(message_events("m6", stream))[0]
        explicit_role = list(message_events("m7", stream, role="user"))[0]

        assert isinstance(default_role, MessageStart)
        assert default_role.role == "assistant"
        assert isinstance(explicit_role, MessageStart)
        assert explicit_role.role == "user"


class TestToolExecutionEvents:
    """tool_execution_*：start 携带调用现场，end 携带真实状态的 Observation（end 与流水线的衔接见流水线测试）。"""

    def test_tool_execution_start_carries_raw_arguments(self) -> None:
        event = ToolExecutionStart(tool_call_id="c1", name="read", arguments='{"path": "a.txt"}')

        assert event.tool_call_id == "c1"
        assert event.name == "read"
        assert event.arguments == '{"path": "a.txt"}'

    def test_tool_execution_update_carries_progress_delta(self) -> None:
        event = ToolExecutionUpdate(tool_call_id="c1", delta="line 1\n")

        assert event.delta == "line 1\n"

    def test_events_are_frozen_protocol_values(self) -> None:
        event = MessageStart(message_id="m1")

        with pytest.raises(FrozenInstanceError):
            event.message_id = "m2"  # type: ignore[misc]

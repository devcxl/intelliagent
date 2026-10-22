"""无头事件序列化契约测试 — Agent 事件 → JSON Lines（无头模式的机器可读事件输出）。"""

from __future__ import annotations

import io
import json

import pytest

from src.core.agent_events import (
    AgentEnd,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
)
from src.core.tool_pipeline import Observation
from src.headless.events import JsonLineSink, delta_to_dict, event_to_dict, observation_to_dict
from src.llm.stream import Error, TextDelta, ToolCallDelta, Usage


def test_boundary_events_serialize_with_event_type() -> None:
    assert event_to_dict(AgentStart()) == {"type": "agent_start"}
    assert event_to_dict(AgentEnd(outcome="settled")) == {"type": "agent_end", "outcome": "settled"}
    assert event_to_dict(TurnStart(turn=3)) == {"type": "turn_start", "turn": 3}
    assert event_to_dict(TurnEnd(turn=3, stop_reason="stop")) == {"type": "turn_end", "turn": 3, "stop_reason": "stop"}


def test_message_events_serialize_deltas() -> None:
    assert event_to_dict(MessageStart(message_id="m1")) == {
        "type": "message_start",
        "message_id": "m1",
        "role": "assistant",
    }
    update = event_to_dict(MessageUpdate(message_id="m1", delta=TextDelta(text="hi")))
    assert update == {"type": "message_update", "message_id": "m1", "delta": {"kind": "text_delta", "text": "hi"}}
    assert event_to_dict(MessageEnd(message_id="m1", stop_reason="length")) == {
        "type": "message_end",
        "message_id": "m1",
        "stop_reason": "length",
        "usage": None,
    }
    assert delta_to_dict(ToolCallDelta(index=0, id="call_1", name="bash", arguments_delta="{")) == {
        "kind": "toolcall_delta",
        "index": 0,
        "id": "call_1",
        "name": "bash",
        "arguments_delta": "{",
    }
    assert delta_to_dict(Error(message="boom")) == {"kind": "error", "message": "boom"}


def test_message_end_serializes_provider_usage() -> None:
    usage = Usage(prompt_tokens=11, completion_tokens=7, total_tokens=18)
    end = MessageEnd(message_id="m1", stop_reason="stop", usage=usage)

    assert event_to_dict(end) == {
        "type": "message_end",
        "message_id": "m1",
        "stop_reason": "stop",
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }
    assert event_to_dict(MessageEnd(message_id="m2", stop_reason="error"))["usage"] is None


def test_tool_execution_events_serialize_arguments_and_observation() -> None:
    start = event_to_dict(ToolExecutionStart(tool_call_id="call_1", name="bash", arguments={"command": "ls"}))
    assert start == {
        "type": "tool_execution_start",
        "tool_call_id": "call_1",
        "name": "bash",
        "arguments": {"command": "ls"},
    }
    observation = Observation(
        tool_call_id="call_1",
        name="bash",
        arguments={"command": "ls"},
        content="ok",
        status="success",
        error=None,
        duration_ms=1.5,
        terminate=False,
    )
    assert observation_to_dict(observation) == {
        "tool_call_id": "call_1",
        "name": "bash",
        "arguments": {"command": "ls"},
        "content": "ok",
        "status": "success",
        "error": None,
        "duration_ms": 1.5,
        "terminate": False,
    }
    end = event_to_dict(ToolExecutionEnd(tool_call_id="call_1", observation=observation))
    assert end["type"] == "tool_execution_end"
    assert end["tool_call_id"] == "call_1"
    assert end["observation"]["status"] == "success"


def test_sink_writes_one_json_object_per_line() -> None:
    stream = io.StringIO()
    sink = JsonLineSink(stream)
    sink.emit(AgentStart())
    sink.emit(AgentEnd(outcome="error"))
    lines = stream.getvalue().splitlines()
    assert [json.loads(line) for line in lines] == [{"type": "agent_start"}, {"type": "agent_end", "outcome": "error"}]


def test_unknown_event_type_is_rejected() -> None:
    with pytest.raises(TypeError):
        event_to_dict(object())  # type: ignore[arg-type]

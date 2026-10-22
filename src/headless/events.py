"""无头事件序列化：Agent 事件 → JSON Lines（无头模式 stdout 的机器可读事件流）。

无头模式的事件输出取 JSON Lines 而非人类可读文本：事件本身就是协议值（src.core.agent_events），
脚本消费需要稳定的机器形态；人类可读诊断一律走 stderr。每行一个 JSON 对象，字段名与事件
dataclass 同名，顶层 "type" 字段取事件族名（agent_start / turn_* / message_* / tool_execution_*），
流式增量在 "delta" 下以 "kind" 区分（text_delta / toolcall_delta / error）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TextIO

from src.core.agent_events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageDelta,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
    TurnEnd,
    TurnStart,
)
from src.core.tool_pipeline import Observation
from src.llm.stream import Error, TextDelta, ToolCallDelta, Usage


def event_to_dict(event: AgentEvent) -> dict[str, Any]:
    """一个事件 → 一个 JSON 可序列化映射；顶层 "type" 字段取事件族名。"""
    if isinstance(event, AgentStart):
        return {"type": "agent_start"}
    if isinstance(event, AgentEnd):
        return {"type": "agent_end", "outcome": event.outcome}
    if isinstance(event, TurnStart):
        return {"type": "turn_start", "turn": event.turn}
    if isinstance(event, TurnEnd):
        return {"type": "turn_end", "turn": event.turn, "stop_reason": event.stop_reason}
    if isinstance(event, MessageStart):
        return {"type": "message_start", "message_id": event.message_id, "role": event.role}
    if isinstance(event, MessageUpdate):
        return {"type": "message_update", "message_id": event.message_id, "delta": delta_to_dict(event.delta)}
    if isinstance(event, MessageEnd):
        return {
            "type": "message_end",
            "message_id": event.message_id,
            "stop_reason": event.stop_reason,
            "usage": _usage_to_dict(event.usage),
        }
    if isinstance(event, ToolExecutionStart):
        return {
            "type": "tool_execution_start",
            "tool_call_id": event.tool_call_id,
            "name": event.name,
            "arguments": _plain(event.arguments),
        }
    if isinstance(event, ToolExecutionUpdate):
        return {"type": "tool_execution_update", "tool_call_id": event.tool_call_id, "delta": event.delta}
    if isinstance(event, ToolExecutionEnd):
        return {
            "type": "tool_execution_end",
            "tool_call_id": event.tool_call_id,
            "observation": observation_to_dict(event.observation),
        }
    raise TypeError(f"unsupported agent event type: {type(event).__name__}")


def delta_to_dict(delta: MessageDelta) -> dict[str, Any]:
    """流式增量 → 映射；"kind" 取增量种类（与 src.llm.stream 的 kind 同名）。"""
    if isinstance(delta, TextDelta):
        return {"kind": "text_delta", "text": delta.text}
    if isinstance(delta, ToolCallDelta):
        return {
            "kind": "toolcall_delta",
            "index": delta.index,
            "id": delta.id,
            "name": delta.name,
            "arguments_delta": delta.arguments_delta,
        }
    if isinstance(delta, Error):
        return {"kind": "error", "message": delta.message}
    raise TypeError(f"unsupported message delta type: {type(delta).__name__}")


def observation_to_dict(observation: Observation) -> dict[str, Any]:
    """Observation 全字段平铺（字段稳定：status/error/terminate 是机器判定依据）。"""
    return {
        "tool_call_id": observation.tool_call_id,
        "name": observation.name,
        "arguments": _plain(observation.arguments),
        "content": observation.content,
        "status": observation.status,
        "error": observation.error,
        "duration_ms": observation.duration_ms,
        "terminate": observation.terminate,
    }


class JsonLineSink:
    """EventSink 的无头实现：每个事件一行 JSON 写入流并立即 flush（脚本可逐行增量消费）。"""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream

    def emit(self, event: AgentEvent) -> None:
        self._stream.write(json.dumps(event_to_dict(event), ensure_ascii=False) + "\n")
        self._stream.flush()


def _plain(arguments: str | Mapping[str, Any]) -> str | dict[str, Any]:
    """arguments 持有的是快照 Mapping（含 mapping proxy），序列化前转普通 dict。"""
    return dict(arguments) if isinstance(arguments, Mapping) else arguments


def _usage_to_dict(usage: Usage | None) -> dict[str, int] | None:
    """usage 平铺为三项计数；无用量时输出 null，不用 0 伪造。"""
    if usage is None:
        return None
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }

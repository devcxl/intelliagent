"""TuiEventSink：引擎事件 → TUI 更新的唯一通道（EventSink 实现，ADR 0009、pi-engine-principles §2）。

TUI 只消费事件流（issue #61）：本模块把 AgentEvent 族翻译成 TuiTarget 的整步刷新调用，
事件顺序即界面更新顺序；不碰持久化、不读 repository。

message_update 的逐块流式渲染是 issue #63——本票原样转交增量，由 MessageView 缓冲后在消息结束时整步刷新。
turn_start/turn_end 是循环边界信号，骨架 UI 不渲染（协议事件不等于渲染事件）。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from src.core.agent_events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    MessageDelta,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    RunOutcome,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
)
from src.core.tool_pipeline import Observation


class TuiTarget(Protocol):
    """TUI 侧的事件落点：TuiEventSink 按事件顺序调用，实现方负责组件更新。"""

    def show_run_started(self) -> None: ...

    def show_run_finished(self, outcome: RunOutcome) -> None: ...

    def show_message_started(self, message_id: str, role: str) -> None: ...

    def show_message_delta(self, message_id: str, delta: MessageDelta) -> None: ...

    def show_message_finished(self, message_id: str) -> None: ...

    def show_tool_started(self, tool_call_id: str, name: str, arguments: str | Mapping[str, Any]) -> None: ...

    def show_tool_progress(self, tool_call_id: str, delta: str) -> None: ...

    def show_tool_finished(self, tool_call_id: str, observation: Observation) -> None: ...


class TuiEventSink:
    """EventSink 实现：把引擎事件翻译成 TuiTarget 调用，无状态、顺序保真。"""

    def __init__(self, target: TuiTarget) -> None:
        self._target = target

    def emit(self, event: AgentEvent) -> None:
        if isinstance(event, AgentStart):
            self._target.show_run_started()
        elif isinstance(event, AgentEnd):
            self._target.show_run_finished(event.outcome)
        elif isinstance(event, MessageStart):
            self._target.show_message_started(event.message_id, event.role)
        elif isinstance(event, MessageUpdate):
            self._target.show_message_delta(event.message_id, event.delta)
        elif isinstance(event, MessageEnd):
            self._target.show_message_finished(event.message_id)
        elif isinstance(event, ToolExecutionStart):
            self._target.show_tool_started(event.tool_call_id, event.name, event.arguments)
        elif isinstance(event, ToolExecutionUpdate):
            self._target.show_tool_progress(event.tool_call_id, event.delta)
        elif isinstance(event, ToolExecutionEnd):
            self._target.show_tool_finished(event.tool_call_id, event.observation)

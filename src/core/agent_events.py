"""Agent 层事件模型：事件是协议而非日志（ADR 0010、pi-engine-principles §2）。

agent / turn / message / tool_execution 四个事件族是引擎与前端、拦截器的共同语言：

- agent_start/agent_end 与 turn_start/turn_end 划分 run 与 turn 边界（turn 边界也是 hook 挂载点）。
- tool_execution_start 在工具执行（含 hook）前发出——permission 拦截与"执行中"状态的基础；
  "先做后播"没有拦截能力，本协议明确禁止。
- message_update 携带流式增量（text/toolcall delta），前端逐块渲染。
- tool_execution_end 携带 Observation（真实状态 success/denied/error）。

事件是冻结 dataclass；投递方式由调用方决定（EventSink 推送或迭代消费 message_events 适配器）。
旧引擎的 dict 事件（src.core.events）随旧引擎在 Phase 7 删除，本模块是其替代协议。
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Protocol

from src.llm.stream import Done, Error, LLMEvent, StopReason, TextDelta, ToolCallDelta

if TYPE_CHECKING:
    from src.core.tool_pipeline import Observation

MessageDelta = TextDelta | ToolCallDelta | Error
"""message_update 携带的流式增量：文本增量、工具调用增量或错误通知（Done 收尾，不进增量）。"""

RunOutcome = Literal["settled", "terminated", "error", "aborted"]
"""一次 run 的收束方式：settled 正常停止 / terminated 工具终止信号 / error、aborted 硬退出。"""


@dataclass(frozen=True)
class AgentStart:
    """一次 run 开始（agent_start）。"""


@dataclass(frozen=True)
class AgentEnd:
    """一次 run 收束（agent_end）：携带收束方式。"""

    outcome: RunOutcome


@dataclass(frozen=True)
class TurnStart:
    """一个 turn 开始（turn_start）：turn 是一次 assistant 响应 + 其工具结果，编号引擎级单调递增。"""

    turn: int


@dataclass(frozen=True)
class TurnEnd:
    """一个 turn 结束（turn_end）：携带该轮响应的终止原因。"""

    turn: int
    stop_reason: StopReason | None = None


@dataclass(frozen=True)
class MessageStart:
    """一条消息开始：前端据此创建渲染单元。"""

    message_id: str
    role: str = "assistant"


@dataclass(frozen=True)
class MessageUpdate:
    """消息的流式增量：delta 就是 LLM 流事件本身，前端逐块渲染，不做二次包装。"""

    message_id: str
    delta: MessageDelta


@dataclass(frozen=True)
class MessageEnd:
    """一条消息结束。stop_reason 是流式响应的终止原因，非流式消息为 None。"""

    message_id: str
    stop_reason: StopReason | None = None


@dataclass(frozen=True)
class ToolExecutionStart:
    """工具执行开始：在任何副作用前发出（含 beforeToolCall），是 permission 拦截的挂载基础。"""

    tool_call_id: str
    name: str
    arguments: str | Mapping[str, Any]


@dataclass(frozen=True)
class ToolExecutionUpdate:
    """工具执行中的流式进度增量。

    当前 ToolSpec handler 尚无进度通道；本事件由支持进度上报的流式工具（T7b 接入）经 EventSink 发出。
    """

    tool_call_id: str
    delta: str


@dataclass(frozen=True)
class ToolExecutionEnd:
    """工具执行结束：携带 Observation，其 status 是真实状态（success/denied/error）。"""

    tool_call_id: str
    observation: Observation


AgentEvent = (
    AgentStart
    | AgentEnd
    | TurnStart
    | TurnEnd
    | MessageStart
    | MessageUpdate
    | MessageEnd
    | ToolExecutionStart
    | ToolExecutionUpdate
    | ToolExecutionEnd
)
"""事件协议的全部消息形态（Agent 层：agent / turn / message / tool_execution 四个事件族）。"""


class EventSink(Protocol):
    """事件消费者接口：TUI、无头模式、测试各自实现；引擎只按协议发出，不关心渲染。"""

    def emit(self, event: AgentEvent) -> None:
        """接收一个事件。"""
        ...


def message_events(message_id: str, stream: Iterable[LLMEvent], *, role: str = "assistant") -> Iterator[AgentEvent]:
    """把一条 LLM 流适配为 message_* 事件族。

    适配规则：MessageStart → 逐个增量的 MessageUpdate → 携带 stop_reason 的 MessageEnd。
    流必须以 Done 收尾（src.llm.stream 契约）；缺失 Done 属于适配器或 LLM 客户端违约，抛 ValueError。

    Args:
        message_id: 消息标识，三种事件共享。
        stream: LLM 流事件序列（TextDelta / ToolCallDelta / Error / Done）。
        role: 消息角色，默认 "assistant"。

    Yields:
        MessageStart、逐个增量的 MessageUpdate、最后携带 stop_reason 的 MessageEnd。
    """
    yield MessageStart(message_id=message_id, role=role)
    stop_reason: StopReason | None = None
    for event in stream:
        if isinstance(event, Done):
            stop_reason = event.stop_reason
            break
        yield MessageUpdate(message_id=message_id, delta=event)
    if stop_reason is None:
        raise ValueError(f"LLM stream for message '{message_id}' ended without Done")
    yield MessageEnd(message_id=message_id, stop_reason=stop_reason)

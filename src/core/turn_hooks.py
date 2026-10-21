"""turn 边界 hook：prepareRequest / prepareNextTurn / finishTurn（ADR 0010、pi-engine-principles §1）。

三个挂载点都是 Hook 能力（CapabilityKind.HOOK），与 before/after 工具 hook 同一注册通道，
按提供者形态（TurnHookProvider）区分挂载点：

- prepareRequest：每次 LLM 请求前。拿到本次请求的可变视图 RequestContext，就地注入只影响本次请求
  （投影语义——注入不写回引擎记录，每轮重新注入不累积）。
- prepareNextTurn：turn 边界（每个已完成 turn 都执行，pi：turn_end 后、循环判定前）。拿到刚完成的
  TurnResult 与当前上下文快照，返回 NextTurnUpdate 整体替换 model / messages / tools
  （对后续所有请求持久生效）。
- finishTurn：turn 结束时。返回 "continue" 要求引擎再跑一轮，即使本轮没有工具调用。

执行顺序与事件边界见 src.core.engine 模块文档。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

from src.llm.stream import ChatMessage, ToolSchema

if TYPE_CHECKING:
    from src.core.tool_pipeline import Observation

FinishDecision = Literal["continue"] | None
"""finishTurn 的裁决："continue" 要求再跑一轮；None 表示按常规判定收束。"""


@dataclass(frozen=True)
class TurnResult:
    """一个已完成 turn 的收束视图：assistant 消息与其工具结果（Observation 真实状态）。"""

    turn: int
    message: ChatMessage
    observations: tuple[Observation, ...]


@dataclass
class RequestContext:
    """一次 LLM 请求的可变视图：prepareRequest 就地注入只影响本次请求，不写回引擎记录。"""

    turn: int
    model: str
    messages: list[ChatMessage]
    tools: list[ToolSchema]


@dataclass(frozen=True)
class NextTurnContext:
    """prepareNextTurn 的输入：刚完成的 turn 结果与当前上下文快照（只读）。"""

    turn: int
    """即将开始的 turn 编号。"""
    result: TurnResult
    model: str
    messages: tuple[ChatMessage, ...]
    tools: tuple[ToolSchema, ...]


@dataclass(frozen=True)
class NextTurnUpdate:
    """prepareNextTurn 的返回：整体替换引擎的 model / messages / tools；None 字段保持不变。"""

    model: str | None = None
    messages: list[ChatMessage] | None = None
    tools: list[ToolSchema] | None = None


class PrepareRequest(Protocol):
    """prepareRequest 挂载回调：每次 LLM 请求前调用，就地改写请求视图（如注入上下文、做压缩阈值检查）。"""

    async def __call__(self, request: RequestContext) -> None: ...


class PrepareNextTurn(Protocol):
    """prepareNextTurn 挂载回调：turn 边界调用，返回 NextTurnUpdate 替换 model/context/tools（如压缩重建）。"""

    async def __call__(self, context: NextTurnContext) -> NextTurnUpdate | None: ...


class FinishTurn(Protocol):
    """finishTurn 挂载回调：turn 结束时调用，返回 "continue" 要求引擎再跑一轮。"""

    async def __call__(self, result: TurnResult) -> FinishDecision: ...


@dataclass(frozen=True)
class PrepareRequestHook:
    """prepareRequest 挂载点的 hook 能力提供者（CONTEXT 术语：Hook）：注册为 CapabilityKind.HOOK。"""

    callback: PrepareRequest


@dataclass(frozen=True)
class PrepareNextTurnHook:
    """prepareNextTurn 挂载点的 hook 能力提供者：注册为 CapabilityKind.HOOK。"""

    callback: PrepareNextTurn


@dataclass(frozen=True)
class FinishTurnHook:
    """finishTurn 挂载点的 hook 能力提供者：注册为 CapabilityKind.HOOK。"""

    callback: FinishTurn


TurnHookProvider = PrepareRequestHook | PrepareNextTurnHook | FinishTurnHook
"""turn 边界 hook 能力提供者的三种形态，按挂载点区分。"""

"""统一流协议：LLMClient 接口与流式事件类型（pi AssistantMessageEvent 简化版）。

事件词汇参照 pi：text_delta / toolcall_delta / done / error（见 docs/pi-engine-principles.md §7）。
两条纪律照搬 pi：错误进流而非同步抛出；usage 逐响应落账（挂在 Done 上）。
每条流以恰好一个 Done 结束，Done.stop_reason 供引擎分类处理（正常结束 / length 截断 / error / aborted）。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol

StopReason = Literal["stop", "length", "error", "aborted"]
EventKind = Literal["text_delta", "toolcall_delta", "done", "error"]


@dataclass(frozen=True)
class Usage:
    """一次模型响应的 token 用量（provider 真实值），供引擎压缩估算。

    Attributes:
        prompt_tokens: 输入 token 数。
        completion_tokens: 输出 token 数。
        total_tokens: 总 token 数。
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True)
class TextDelta:
    """流式文本增量（token 级）。"""

    text: str
    kind: ClassVar[EventKind] = "text_delta"


@dataclass(frozen=True)
class ToolCallDelta:
    """流式工具调用增量：id/name 只在首个增量出现，arguments_delta 是逐段 JSON 片段。"""

    index: int
    id: str | None
    name: str | None
    arguments_delta: str
    kind: ClassVar[EventKind] = "toolcall_delta"


@dataclass(frozen=True)
class Error:
    """错误进流：不可重试或重试耗尽后发出，之后以 Done(stop_reason="error") 收尾。"""

    message: str
    kind: ClassVar[EventKind] = "error"


@dataclass(frozen=True)
class Done:
    """响应终止事件：每条流恰好一个，携带 stopReason 与本响应 usage。

    Attributes:
        stop_reason: "stop" 正常结束（含 tool_calls）；"length" 截断；"error" 出错；"aborted" 中止。
        usage: 本响应 token 用量；error/aborted 可能为 None。
    """

    stop_reason: StopReason
    usage: Usage | None
    kind: ClassVar[EventKind] = "done"


LLMEvent = TextDelta | ToolCallDelta | Error | Done

ChatMessage = dict[str, Any]
ToolSchema = dict[str, Any]


@dataclass(frozen=True)
class StreamRequest:
    """一次模型请求。messages/tools 采用 litellm 统一（OpenAI chat）格式，provider 差异由 litellm 收敛。

    Attributes:
        model: litellm 的 model 字符串，如 "openai/gpt-4o"、"deepseek/deepseek-chat"。
        messages: 发给模型的消息列表。
        tools: 工具 schema 列表（function calling）。
        temperature: 采样温度，None 表示不传。
        max_tokens: 最大输出 token 数，None 表示不限制。
    """

    model: str
    messages: list[ChatMessage]
    tools: list[ToolSchema] | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class LLMClient(Protocol):
    """统一流协议接口：产出流式事件，每条流以恰好一个 Done 结束。

    错误（含超时重试耗尽）编码进流（Error + Done(stop_reason="error")），不从 stream() 同步抛出。
    """

    def stream(self, request: StreamRequest, *, abort: threading.Event | None = None) -> Iterator[LLMEvent]:
        """产出一次模型响应的流式事件序列。

        Args:
            request: 模型请求。
            abort: 中止信号；置位后流以 Done(stop_reason="aborted") 尽快结束。

        Returns:
            流式事件迭代器：text/toolcall 增量在前，Done 收尾（出错时 Error 先于 Done）。
        """
        ...

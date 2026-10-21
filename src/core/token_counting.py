"""Token 估算与 usage 计数（从 compaction 拆出，独立可测）。

estimate_tokens 是 pi estimateTokens 的 chars/4 估算；TokenCounter 以 provider 真实
usage 为基线估算上下文大小；UsageRecordingClient 观察流的 Done.usage 喂给计数器。
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterator, Sequence

from src.llm.stream import Done, LLMClient, LLMEvent, StreamRequest, Usage

ChatMessage = dict[str, object]


def estimate_tokens(message: ChatMessage) -> int:
    """单条消息的 token 估算（pi estimateTokens）：正文与 tool_call 的 name/arguments 按 chars/4。"""
    chars = len(str(message.get("content") or ""))
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        chars += len(str(function.get("name") or "")) + len(str(function.get("arguments") or ""))
    return math.ceil(chars / 4)


class TokenCounter:
    """上下文 token 计数：真实 usage 基线 + 基线外消息的 chars/4 估算（pi estimateContextTokens）。

    基线是最近一次响应的 provider 真实 usage 与其覆盖的消息前缀；新响应重新定基线而不累计。
    """

    def __init__(self, *, overhead_tokens: int = 0) -> None:
        self._baseline: tuple[int, tuple[ChatMessage, ...]] | None = None
        self._overhead_tokens = overhead_tokens

    def record(self, usage: Usage | None, covered: Sequence[ChatMessage]) -> None:
        """记录一次模型响应的真实 usage 与它覆盖的消息前缀；无有效 usage 时清除基线。"""
        if usage is None or usage.prompt_tokens <= 0:
            self._baseline = None
            return
        self._baseline = (usage.prompt_tokens, tuple(dict(message) for message in covered))

    def estimate(self, messages: Sequence[ChatMessage]) -> int:
        """估算消息列表的上下文 token：基线 + 基线外消息估算；基线失配退回整体估算。

        回退估算含 overhead（system prompt + 工具 schema 的 chars/4 近似）——真实 usage
        基线隐含这部分，纯消息估算会系统性低估触发阈值。
        """
        if self._baseline is not None:
            base, covered = self._baseline
            if _is_prefix(covered, messages):
                return base + sum(estimate_tokens(message) for message in messages[len(covered) :])
        return sum(estimate_tokens(message) for message in messages) + self._overhead_tokens


class UsageRecordingClient:
    """LLMClient 装饰器：观察每条流的 Done.usage 喂给 TokenCounter，事件原样透传。

    引擎（src/core/engine.py）不感知压缩；usage 消费靠这个装饰器与引擎之间的 seam。
    """

    def __init__(self, inner: LLMClient, counter: TokenCounter) -> None:
        self._inner = inner
        self._counter = counter

    def stream(self, request: StreamRequest, *, abort: threading.Event | None = None) -> Iterator[LLMEvent]:
        for event in self._inner.stream(request, abort=abort):
            if isinstance(event, Done):
                self._counter.record(event.usage, request.messages)
            yield event


def _is_prefix(covered: Sequence[ChatMessage], messages: Sequence[ChatMessage]) -> bool:
    return len(covered) <= len(messages) and all(a == b for a, b in zip(covered, messages))

from __future__ import annotations

from typing import Any, Protocol


class LLMResponseProto:
    """LLM 响应协议类型（duck typing，非 Pydantic 模型）。

    Attributes:
        content: 响应文本内容
        tool_calls: 工具调用列表
        usage: Token 用量信息
    """

    content: str | None
    tool_calls: list[Any]
    usage: Any | None


class LLMClientProtocol(Protocol):
    """LLM 客户端协议 — ReactEngine 依赖的最小接口。"""

    async def chat_async(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponseProto: ...


__all__ = [
    "LLMResponseProto",
    "LLMClientProtocol",
]

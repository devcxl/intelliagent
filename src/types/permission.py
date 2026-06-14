from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel


class PermissionAction(str, Enum):
    """权限动作枚举。

    定义权限系统支持的动作类型：
    - allow: 允许执行
    - deny: 拒绝执行
    - ask: 需要用户确认
    """

    allow = "allow"
    deny = "deny"
    ask = "ask"


class Decision(BaseModel):
    """权限决策结果。

    Attributes:
        action: 决策动作（allow/deny/ask）
        reason: 决策原因说明
    """

    action: PermissionAction = PermissionAction.ask
    reason: str = ""


class PermissionCallback(ABC):
    """权限确认回调抽象基类。

    子类需实现 on_prompt 方法，在 ask 决策时向用户发起确认。
    """

    @abstractmethod
    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool: ...


# ---------------------------------------------------------------------------
# Protocol 定义 — 为 ReactEngine 提供类型契约
# ---------------------------------------------------------------------------


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


class MemoryProtocol(Protocol):
    def clear_memory(self) -> None: ...
    def add_observation(self, obs: dict[str, Any]) -> None: ...


class PermissionEngineProtocol(Protocol):
    def check(self, tool_name: str, args: dict[str, Any]) -> Decision: ...


class PermissionCallbackProtocol(Protocol):
    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool: ...


__all__ = [
    "PermissionAction",
    "Decision",
    "PermissionCallback",
    "LLMClientProtocol",
    "MemoryProtocol",
    "PermissionEngineProtocol",
    "PermissionCallbackProtocol",
    "LLMResponseProto",
]

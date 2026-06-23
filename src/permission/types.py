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


class PermissionEngineProtocol(Protocol):
    def check(self, tool_name: str, args: dict[str, Any]) -> Decision: ...


class PermissionCallbackProtocol(Protocol):
    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool: ...


__all__ = [
    "PermissionAction",
    "Decision",
    "PermissionCallback",
    "PermissionEngineProtocol",
    "PermissionCallbackProtocol",
]

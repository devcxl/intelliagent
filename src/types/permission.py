from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field


class PermissionAction(str, Enum):
    allow = "allow"
    deny = "deny"
    prompt = "prompt"


class Decision(BaseModel):
    action: PermissionAction = PermissionAction.prompt
    reason: str = ""


class Rule(BaseModel):
    tool: str
    action: PermissionAction = PermissionAction.prompt
    conditions: dict[str, Any] = Field(default_factory=dict)


class PermissionCallback(ABC):
    @abstractmethod
    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        ...


# ---------------------------------------------------------------------------
# Protocol 定义 — 为 ReactEngine 提供类型契约
# ---------------------------------------------------------------------------

class LLMResponseProto:
    content: str | None
    tool_calls: list[Any]
    usage: Any | None


class LLMClientProtocol(Protocol):
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
    "PermissionAction", "Decision", "Rule", "PermissionCallback",
    "LLMClientProtocol", "MemoryProtocol", "PermissionEngineProtocol",
    "PermissionCallbackProtocol", "LLMResponseProto",
]

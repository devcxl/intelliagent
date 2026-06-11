from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

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

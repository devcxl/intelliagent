"""插件 Manifest：声明式描述插件名称、版本、api_version、能力清单与配置 schema。"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

NAME_PATTERN = r"^[a-z0-9][a-z0-9._-]*$"


class CapabilityKind(str, Enum):
    """插件可注册的能力类型（CONTEXT 术语：Capability）。"""

    TOOL = "tool"
    HOOK = "hook"
    PERMISSION = "permission"
    STORAGE = "storage"


class CapabilityDeclaration(BaseModel):
    """Manifest 中的一条能力声明。"""

    model_config = ConfigDict(frozen=True)

    kind: CapabilityKind
    name: str = Field(pattern=NAME_PATTERN)


class Manifest(BaseModel):
    """插件的声明式描述（CONTEXT 术语：Manifest）。

    capabilities 是插件承诺注册的完整能力清单：注册缺失或多注册都会被宿主拒绝。
    config_schema 是插件配置的 pydantic 模型；为 None 表示插件不接受任何配置。
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(pattern=NAME_PATTERN)
    version: str = Field(min_length=1)
    api_version: int = Field(ge=1)
    capabilities: tuple[CapabilityDeclaration, ...] = Field(min_length=1)
    config_schema: type[BaseModel] | None = None

    @model_validator(mode="after")
    def _reject_duplicate_capabilities(self) -> Manifest:
        seen: set[tuple[CapabilityKind, str]] = set()
        for declaration in self.capabilities:
            key = (declaration.kind, declaration.name)
            if key in seen:
                raise ValueError(f"capability '{declaration.kind.value}:{declaration.name}' is declared more than once")
            seen.add(key)
        return self

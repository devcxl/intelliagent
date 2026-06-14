#!/usr/bin/env python3
"""统一配置模型 — 所有配置域收敛到单一 intelliagent.json。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.config.env_interpolator import deep_interpolate


class LLMConfig(BaseModel):
    """LLM 客户端配置。"""

    api_key: str = ""
    base_url: str | None = None
    model: str = "gpt-4o-mini"


class WorkspaceConfig(BaseModel):
    """工作区配置。"""

    dir: str = "."


class DatabaseConfig(BaseModel):
    """数据库配置。"""

    url: str = "sqlite:///intelliagent.db"


class PermissionRule(BaseModel):
    """单条权限规则 — pattern + action 模式。"""

    pattern: str = "*"
    action: Literal["allow", "ask", "deny"] = "ask"


class PermissionsConfig(BaseModel):
    """权限规则集合。"""

    rules: list[PermissionRule] = Field(default_factory=list)
    external_directories: list[str] = Field(default_factory=list)


class UnifiedConfig(BaseModel):
    """统一配置模型 — 涵盖所有子配置域。

    通过 `UnifiedConfig.load(path)` 从 intelliagent.json 加载，
    自动执行 {env:NAME} 插值展开。
    """

    llm: LLMConfig = Field(default_factory=LLMConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    experience_file: str = "experiences.json"
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    mcp: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = "intelliagent.json") -> UnifiedConfig:
        """从 JSON 文件加载配置，自动执行环境变量插值。

        文件不存在时返回全默认值。
        """
        path = Path(path)
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        interpolated = deep_interpolate(raw)
        return cls.model_validate(interpolated)

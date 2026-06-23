#!/usr/bin/env python3
"""统一配置模型 — 所有配置域收敛到单一 intelliagent.json。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.config.env_interpolator import deep_interpolate
from src.config.provider_config import ProviderConfig


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


class SkillsConfig(BaseModel):
    """Skill 系统配置。

    Attributes:
        enabled: 是否启用 skills 功能
        project_paths: 项目级 skill 扫描路径
        user_paths: 用户级 skill 扫描路径
    """

    enabled: bool = True
    project_paths: list[str] = Field(default_factory=lambda: [".agents/skills"])
    user_paths: list[str] = Field(default_factory=lambda: ["~/.config/opencode/skills"])


class UnifiedConfig(BaseModel):
    """统一配置模型 — 涵盖所有子配置域。

    通过 `UnifiedConfig.load(path)` 从 intelliagent.json 加载，
    自动执行 {env:NAME} 插值展开。
    """

    model: str | None = None
    small_model: str | None = None
    provider: dict[str, ProviderConfig] = Field(default_factory=dict)
    enabled_providers: list[str] | None = None
    disabled_providers: list[str] | None = None

    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    mcp: dict[str, Any] = Field(default_factory=dict)

    def get_model_context_limit(self) -> int | None:
        """从 model 引用解析模型上下文长度限制。

        model 格式为 "provider_id/model_id"。
        查询顺序：① 用户配置覆盖 → ② 注册表数据 → ③ 返回 None。
        """
        if not self.model or "/" not in self.model:
            return None
        provider_id, model_id = self.model.split("/", 1)

        # ① 用户配置覆盖
        pc = self.provider.get(provider_id)
        if pc and pc.models:
            mo = pc.models.get(model_id)
            if mo and mo.limit and mo.limit.context is not None:
                return mo.limit.context

        # ② 注册表数据
        from src.config.provider_registry import ProviderRegistry

        return ProviderRegistry.get_model_context_limit(provider_id, model_id)

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

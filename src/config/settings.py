#!/usr/bin/env python3
"""
统一配置定义。

仅从 intelliagent.json 加载，不再支持 .env / BaseSettings 向后兼容。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.config.unified_config import UnifiedConfig


DEFAULT_DATABASE_URL = "sqlite:///intelliagent.db"
INTELLIAGENT_CONFIG_FILE = "intelliagent.json"


class Settings(BaseModel):
    """项目配置桥接层 — 从 UnifiedConfig 构造。

    仅作为过渡层存在，后续可直接使用 UnifiedConfig 替代。
    """

    LOG_LEVEL: str = "INFO"

    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    EXPERIENCE_FILE: str = "experiences.json"

    WORKSPACE_DIR: str = Field(default_factory=lambda: str(Path.cwd()))

    DATABASE_URL: str = Field(default=DEFAULT_DATABASE_URL)

    @classmethod
    def from_unified_config(cls, config: UnifiedConfig) -> Settings:
        """从 UnifiedConfig 构造 Settings 实例。"""
        return cls(
            OPENAI_API_KEY=config.llm.api_key,
            OPENAI_API_BASE=config.llm.base_url,
            OPENAI_MODEL=config.llm.model,
            WORKSPACE_DIR=config.workspace.dir,
            DATABASE_URL=config.database.url,
            EXPERIENCE_FILE=config.experience_file,
        )


_ENV_OVERRIDE_KEYS = [
    "OPENAI_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_MODEL",
    "WORKSPACE_DIR",
    "DATABASE_URL",
    "EXPERIENCE_FILE",
    "LOG_LEVEL",
]


def _collect_env_overrides() -> dict[str, str]:
    """收集环境变量中与 Settings 字段对应的覆盖值。"""
    overrides: dict[str, str] = {}
    for key in _ENV_OVERRIDE_KEYS:
        val = os.environ.get(key)
        if val is not None:
            overrides[key] = val
    return overrides


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取缓存后的配置实例。

    从 intelliagent.json 加载，环境变量覆盖。
    """
    from src.config.unified_config import UnifiedConfig

    unified = UnifiedConfig.load(INTELLIAGENT_CONFIG_FILE)
    settings = Settings.from_unified_config(unified)

    # 环境变量覆盖：真实环境变量优先级高于 JSON 文件
    env_overrides = _collect_env_overrides()
    for key, value in env_overrides.items():
        setattr(settings, key, value)

    return settings


def clear_settings_cache() -> None:
    """测试场景下清理缓存。"""
    get_settings.cache_clear()

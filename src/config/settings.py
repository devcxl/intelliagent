#!/usr/bin/env python3
"""
统一配置定义。

PR1 先将现有环境变量收敛到 Pydantic Settings，后续阶段再继续拆分到
更细粒度的 runtime / db / web 配置边界。
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import Field

if TYPE_CHECKING:
    from src.config.unified_config import UnifiedConfig

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - 兼容未安装 pydantic-settings 的环境
    from pydantic import BaseSettings  # type: ignore

    SettingsConfigDict = None


DEFAULT_DATABASE_URL = "sqlite:///intelliagent.db"
INTELLIAGENT_CONFIG_FILE = "intelliagent.json"

_logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """项目统一配置。

    可通过 from_unified_config() 从 UnifiedConfig 构造，
    也可直接从环境变量 /.env 加载（向后兼容）。
    """

    LOG_LEVEL: str = "INFO"

    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    EXPERIENCE_FILE: str = "experiences.json"

    WORKSPACE_DIR: str = Field(default_factory=lambda: str(Path.cwd()))
    PERMISSION_CONFIG: str = "permissions.json"

    DATABASE_URL: str = Field(default=DEFAULT_DATABASE_URL)

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            extra="ignore",
        )
    else:

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            extra = "ignore"

    @classmethod
    def from_unified_config(cls, config: UnifiedConfig) -> Settings:
        """从 UnifiedConfig 构造 Settings 实例（桥接层）。"""
        return cls(
            OPENAI_API_KEY=config.llm.api_key,
            OPENAI_API_BASE=config.llm.base_url,
            OPENAI_MODEL=config.llm.model,
            WORKSPACE_DIR=config.workspace.dir,
            DATABASE_URL=config.database.url,
            EXPERIENCE_FILE=config.experience_file,
        )


def _has_old_config_files() -> bool:
    """检查是否存在旧版配置文件。"""
    return os.path.isfile(".env") or os.path.isfile("permissions.json") or os.path.isfile("mcp_config.json")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取缓存后的配置实例。

    加载优先级：
    1. intelliagent.json 存在 → 从 UnifiedConfig 加载，环境变量覆盖
    2. intelliagent.json 不存在 → 旧行为（Pydantic Settings），打印 deprecation warning
    """
    if os.path.isfile(INTELLIAGENT_CONFIG_FILE):
        from src.config.unified_config import UnifiedConfig

        unified = UnifiedConfig.load(INTELLIAGENT_CONFIG_FILE)
        settings = Settings.from_unified_config(unified)

        # 环境变量覆盖：真实环境变量优先级高于 JSON 文件
        env_overrides = _collect_env_overrides()
        for key, value in env_overrides.items():
            setattr(settings, key, value)

        return settings

    # 向后兼容：旧文件方式
    if _has_old_config_files():
        _logger.warning(
            "检测到旧版配置文件（.env / permissions.json / mcp_config.json），"
            "请迁移到 intelliagent.json。详见 intelliagent.json.example。"
        )

    return Settings()


def _collect_env_overrides() -> dict[str, str]:
    """收集环境变量中与 Settings 字段对应的覆盖值。"""
    env_map = {
        "OPENAI_API_KEY": "OPENAI_API_KEY",
        "OPENAI_API_BASE": "OPENAI_API_BASE",
        "OPENAI_MODEL": "OPENAI_MODEL",
        "WORKSPACE_DIR": "WORKSPACE_DIR",
        "DATABASE_URL": "DATABASE_URL",
        "EXPERIENCE_FILE": "EXPERIENCE_FILE",
        "LOG_LEVEL": "LOG_LEVEL",
    }
    overrides: dict[str, str] = {}
    for env_key, settings_key in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            overrides[settings_key] = val
    return overrides


def clear_settings_cache() -> None:
    """测试场景下清理缓存。"""
    get_settings.cache_clear()

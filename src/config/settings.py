#!/usr/bin/env python3
"""
统一配置定义。

PR1 先将现有环境变量收敛到 Pydantic Settings，后续阶段再继续拆分到
更细粒度的 runtime / db / web 配置边界。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict
except ImportError:  # pragma: no cover - 兼容未安装 pydantic-settings 的环境
    from pydantic import BaseSettings  # type: ignore

    SettingsConfigDict = None


DEFAULT_DATABASE_URL = "sqlite:///intelliagent.db"


class Settings(BaseSettings):
    """项目统一配置。"""

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取缓存后的配置实例。"""
    return Settings()


def clear_settings_cache() -> None:
    """测试场景下清理缓存。"""
    get_settings.cache_clear()

#!/usr/bin/env python3
"""统一配置测试。"""

import json
from pathlib import Path

import pytest

from src.config import clear_settings_cache, get_settings
from src.config.unified_config import UnifiedConfig
from src.db.manager import resolve_sqlite_database_path


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    clear_settings_cache()

    settings = get_settings()

    assert settings.OPENAI_MODEL == "test-model"
    assert settings.LOG_LEVEL == "DEBUG"

    clear_settings_cache()


def test_settings_default_database_url_uses_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    clear_settings_cache()

    settings = get_settings()

    assert settings.DATABASE_URL.startswith("sqlite:///")

    clear_settings_cache()


def test_settings_relative_database_url_resolves_from_cwd(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///data/test.db")
    clear_settings_cache()

    settings = get_settings()

    assert resolve_sqlite_database_path(settings.DATABASE_URL) == (Path.cwd() / "data/test.db")

    clear_settings_cache()


def test_settings_absolute_database_url_is_preserved(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/intelliagent-test.db")
    clear_settings_cache()

    settings = get_settings()

    assert str(resolve_sqlite_database_path(settings.DATABASE_URL)) == "/tmp/intelliagent-test.db"

    clear_settings_cache()


def test_settings_rejects_non_sqlite_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    clear_settings_cache()

    settings = get_settings()

    with pytest.raises(ValueError):
        resolve_sqlite_database_path(settings.DATABASE_URL)

    clear_settings_cache()


# ============================================================================
# 新增：from_unified_config 桥接测试
# ============================================================================


def test_from_unified_config_maps_provider_fields():
    from src.config.settings import Settings

    unified = UnifiedConfig.model_validate(
        {
            "model": "bridge-model",
            "provider": {
                "openai": {
                    "options": {
                        "apiKey": "sk-bridge",
                        "baseURL": "https://api.example.com",
                    },
                },
            },
        }
    )
    settings = Settings.from_unified_config(unified)

    assert settings.OPENAI_API_KEY == "sk-bridge"
    assert settings.OPENAI_API_BASE == "https://api.example.com"
    assert settings.OPENAI_MODEL == "bridge-model"


def test_from_unified_config_maps_workspace_and_database():
    from src.config.settings import Settings

    unified = UnifiedConfig.model_validate(
        {
            "workspace": {"dir": "/tmp/ws"},
            "database": {"url": "sqlite:///bridge.db"},
        }
    )
    settings = Settings.from_unified_config(unified)

    assert settings.WORKSPACE_DIR == "/tmp/ws"
    assert settings.DATABASE_URL == "sqlite:///bridge.db"


def test_from_unified_config_uses_defaults_for_missing_fields():
    from src.config.settings import Settings

    unified = UnifiedConfig()
    settings = Settings.from_unified_config(unified)

    assert settings.OPENAI_API_KEY == ""
    assert settings.OPENAI_MODEL == ""
    assert settings.DATABASE_URL == "sqlite:///intelliagent.db"


def test_get_settings_loads_from_intelliagent_json(tmp_path, monkeypatch):
    """当 intelliagent.json 存在时，get_settings() 应从它加载。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")

    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "model": "custom-model",
                "provider": {
                    "openai": {
                        "options": {
                            "apiKey": "{env:OPENAI_API_KEY}",
                        },
                    },
                },
            }
        )
    )
    clear_settings_cache()

    settings = get_settings()
    assert settings.OPENAI_API_KEY == "sk-from-env"
    assert settings.OPENAI_MODEL == "custom-model"

    clear_settings_cache()


def test_get_settings_env_overrides_intelliagent_json(tmp_path, monkeypatch):
    """真实环境变量应覆盖 intelliagent.json 中的值。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_MODEL", "env-model-override")

    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "llm": {"model": "json-model"},
            }
        )
    )
    clear_settings_cache()

    settings = get_settings()
    assert settings.OPENAI_MODEL == "env-model-override"

    clear_settings_cache()

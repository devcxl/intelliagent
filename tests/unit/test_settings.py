#!/usr/bin/env python3
"""统一配置测试。"""

from pathlib import Path

import pytest

from src.config import clear_settings_cache, get_settings
from src.db.manager import resolve_sqlite_database_path


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("WEB_PORT", "9001")
    clear_settings_cache()

    settings = get_settings()

    assert settings.OPENAI_MODEL == "test-model"
    assert settings.WEB_PORT == 9001

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

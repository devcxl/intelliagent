#!/usr/bin/env python3
"""env_interpolator 单元测试 — 覆盖 {env:NAME} / {env:NAME:default} 插值语法。"""

import pytest

from src.config.env_interpolator import deep_interpolate, interpolate

# ============================================================================
# interpolate() — 单字符串插值
# ============================================================================


def test_interpolate_replaces_env_var(monkeypatch):
    monkeypatch.setenv("TEST_VAR", "hello")
    assert interpolate("{env:TEST_VAR}") == "hello"


def test_interpolate_uses_default_when_env_missing(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    assert interpolate("{env:MISSING_VAR:fallback}") == "fallback"


def test_interpolate_raises_when_no_env_and_no_default(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    with pytest.raises(ValueError, match="环境变量 MISSING_VAR 未设置"):
        interpolate("{env:MISSING_VAR}")


def test_interpolate_preserves_non_env_text():
    assert interpolate("just a normal string") == "just a normal string"


def test_interpolate_empty_string():
    assert interpolate("") == ""


def test_interpolate_multiple_vars_in_one_string(monkeypatch):
    monkeypatch.setenv("A", "alpha")
    monkeypatch.setenv("B", "beta")
    assert interpolate("{env:A}-{env:B}") == "alpha-beta"


def test_interpolate_mixed_env_and_literal(monkeypatch):
    monkeypatch.setenv("HOST", "localhost")
    assert interpolate("http://{env:HOST}:8080") == "http://localhost:8080"


def test_interpolate_default_with_colon_in_value(monkeypatch):
    """默认值中包含冒号（如 URL）不应被截断。"""
    monkeypatch.delenv("DB", raising=False)
    result = interpolate("{env:DB:postgresql://localhost:5432/db}")
    assert result == "postgresql://localhost:5432/db"


def test_interpolate_env_var_value_contains_braces(monkeypatch):
    """环境变量值包含花括号时不应被二次解析。"""
    monkeypatch.setenv("JSON_FRAGMENT", '{"key": "value"}')
    assert interpolate("{env:JSON_FRAGMENT}") == '{"key": "value"}'


def test_interpolate_partial_match_not_replaced():
    """不完整的 {env: 前缀不应被替换。"""
    assert interpolate("not-a-var{env:}") == "not-a-var{env:}"


# ============================================================================
# deep_interpolate() — 递归结构插值
# ============================================================================


def test_deep_interpolate_dict(monkeypatch):
    monkeypatch.setenv("KEY", "secret")
    data = {"api_key": "{env:KEY}", "model": "gpt-4o-mini"}
    result = deep_interpolate(data)
    assert result == {"api_key": "secret", "model": "gpt-4o-mini"}


def test_deep_interpolate_nested_dict(monkeypatch):
    monkeypatch.setenv("TOKEN", "abc123")
    data = {"llm": {"api_key": "{env:TOKEN}"}}
    result = deep_interpolate(data)
    assert result == {"llm": {"api_key": "abc123"}}


def test_deep_interpolate_list(monkeypatch):
    monkeypatch.setenv("X", "10")
    data = ["{env:X}", "literal", "{env:X:5}"]
    result = deep_interpolate(data)
    assert result == ["10", "literal", "10"]


def test_deep_interpolate_nested_list_in_dict(monkeypatch):
    monkeypatch.setenv("CMD", "npx")
    data = {"servers": [{"command": "{env:CMD}", "args": ["-y", "{env:CMD:node}"]}]}
    result = deep_interpolate(data)
    assert result == {"servers": [{"command": "npx", "args": ["-y", "npx"]}]}


def test_deep_interpolate_non_string_passthrough():
    data = {"count": 42, "enabled": True, "ratio": 3.14, "nothing": None}
    result = deep_interpolate(data)
    assert result == data


def test_deep_interpolate_empty_dict():
    assert deep_interpolate({}) == {}


def test_deep_interpolate_empty_list():
    assert deep_interpolate([]) == []


def test_deep_interpolate_raises_on_missing_env_in_nested(monkeypatch):
    monkeypatch.delenv("REQUIRED", raising=False)
    with pytest.raises(ValueError, match="环境变量 REQUIRED 未设置"):
        deep_interpolate({"key": "{env:REQUIRED}"})

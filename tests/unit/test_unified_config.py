#!/usr/bin/env python3
"""UnifiedConfig 单元测试 — 覆盖统一配置加载、默认值、向后兼容。"""

import json

import pytest

from src.config.unified_config import (
    AgentTeamConfig,
    DatabaseConfig,
    PermissionRule,
    PermissionsConfig,
    UnifiedConfig,
    WorkspaceConfig,
)

# ============================================================================
# 子模型默认值
# ============================================================================


def test_workspace_config_defaults():
    config = WorkspaceConfig()
    assert config.dir == "."


def test_database_config_defaults():
    config = DatabaseConfig()
    assert config.url == "sqlite:///intelliagent.db"


def test_permission_rule_defaults():
    rule = PermissionRule()
    assert rule.pattern == "*"
    assert rule.action == "ask"


def test_permissions_config_defaults():
    config = PermissionsConfig()
    assert config.rules == []


def test_agent_team_config_defaults():
    config = AgentTeamConfig()
    assert config.enabled is False


# ============================================================================
# UnifiedConfig 全默认值
# ============================================================================


def test_unified_config_defaults():
    config = UnifiedConfig()
    assert config.model is None
    assert config.workspace.dir == "."
    assert config.database.url == "sqlite:///intelliagent.db"
    assert config.permissions.rules == []
    assert config.agent_team.enabled is False
    assert config.mcp == {}
    assert config.provider == {}


# ============================================================================
# UnifiedConfig.load() — 文件存在时
# ============================================================================


def test_load_from_valid_json(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")

    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "model": "{env:OPENAI_MODEL:gpt-4o-mini}",
                "provider": {
                    "openai": {
                        "options": {
                            "apiKey": "{env:OPENAI_API_KEY}",
                        },
                    },
                },
                "workspace": {"dir": "/tmp/ws"},
                "database": {"url": "sqlite:///test.db"},
                "permissions": {
                    "rules": [
                        {"pattern": "run_shell", "action": "deny"},
                    ],
                },
                "mcp": {
                    "servers": [
                        {"name": "fs", "command": "npx", "args": ["-y", "server-fs"]},
                    ],
                },
            }
        )
    )

    config = UnifiedConfig.load(str(config_path))

    assert config.model == "gpt-4o"
    assert config.provider["openai"].options.apiKey == "sk-test-123"
    assert config.workspace.dir == "/tmp/ws"
    assert config.database.url == "sqlite:///test.db"
    assert len(config.permissions.rules) == 1
    assert config.permissions.rules[0].pattern == "run_shell"
    assert config.permissions.rules[0].action == "deny"
    assert config.mcp["servers"][0]["name"] == "fs"


def test_load_agent_team_enabled(tmp_path):
    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(json.dumps({"agent_team": {"enabled": True}}))

    config = UnifiedConfig.load(str(config_path))

    assert config.agent_team.enabled is True


def test_load_from_missing_file_returns_defaults():
    config = UnifiedConfig.load("/tmp/nonexistent_intelliagent.json")
    assert config.model is None
    assert config.workspace.dir == "."
    assert config.permissions.rules == []


def test_load_with_env_default_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "model": "{env:OPENAI_MODEL:gpt-4o-mini}",
            }
        )
    )

    config = UnifiedConfig.load(str(config_path))
    assert config.model == "gpt-4o-mini"


def test_load_raises_on_missing_required_env(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "provider": {
                    "openai": {
                        "options": {"apiKey": "{env:OPENAI_API_KEY}"},
                    },
                },
            }
        )
    )

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        UnifiedConfig.load(str(config_path))


def test_load_invalid_json_raises(tmp_path):
    config_path = tmp_path / "intelliagent.json"
    config_path.write_text("not valid json")

    with pytest.raises(json.JSONDecodeError):
        UnifiedConfig.load(str(config_path))


def test_load_invalid_schema_raises_validation_error(tmp_path):
    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "model": 12345,
            }
        )
    )

    with pytest.raises(Exception):
        UnifiedConfig.load(str(config_path))


def test_load_permissions_with_pattern(tmp_path):
    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "permissions": {
                    "rules": [
                        {
                            "pattern": "read *",
                            "action": "allow",
                        },
                    ],
                },
            }
        )
    )

    config = UnifiedConfig.load(str(config_path))
    rule = config.permissions.rules[0]
    assert rule.pattern == "read *"
    assert rule.action == "allow"


def test_load_mcp_servers_preserved_as_dict(tmp_path):
    config_path = tmp_path / "intelliagent.json"
    config_path.write_text(
        json.dumps(
            {
                "mcp": {
                    "servers": [
                        {
                            "name": "github",
                            "command": "npx",
                            "args": ["-y", "server-github"],
                            "env": {"GITHUB_TOKEN": "{env:GITHUB_TOKEN:default}"},
                        },
                    ],
                },
            }
        )
    )

    config = UnifiedConfig.load(str(config_path))
    server = config.mcp["servers"][0]
    assert server["name"] == "github"
    assert server["env"]["GITHUB_TOKEN"] == "default"

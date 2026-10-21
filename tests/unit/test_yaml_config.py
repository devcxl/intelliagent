#!/usr/bin/env python3
"""yaml_config 单元测试 — 覆盖 YAML 解析、{env:NAME} 插值、plugins 段与诊断错误。"""

from pathlib import Path

import pytest

from src.config.yaml_config import ConfigError, interpolate_env, load_config

# ============================================================================
# 辅助
# ============================================================================


def _write_config(tmp_path: Path, content: str, name: str = "intelliagent.yaml") -> Path:
    config_path = tmp_path / name
    config_path.write_text(content, encoding="utf-8")
    return config_path


# ============================================================================
# 解析
# ============================================================================


def test_empty_file_yields_defaults(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, ""))
    assert config.default_model is None
    assert config.providers == {}
    assert config.max_steps is None
    assert config.workspace.dir == "."
    assert config.plugins == {}


def test_parses_top_level_fields(tmp_path: Path) -> None:
    content = (
        "default_model: local/model\n"
        "max_steps: 20\n"
        "workspace:\n"
        "  dir: /srv/ws\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        "    api: http://127.0.0.1:8000/v1\n"
        "    models:\n"
        "      model:\n"
        "        id: wire-model\n"
    )
    config = load_config(_write_config(tmp_path, content))
    assert config.default_model == "local/model"
    assert config.providers["local"].type == "openai-compatible"
    assert config.providers["local"].models["model"].id == "wire-model"
    assert config.max_steps == 20
    assert config.workspace.dir == "/srv/ws"


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="intelliagent.yaml"):
        load_config(tmp_path / "intelliagent.yaml")


def test_non_mapping_root_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="顶层"):
        load_config(_write_config(tmp_path, "- just\n- a\n- list\n"))


def test_malformed_yaml_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="YAML"):
        load_config(_write_config(tmp_path, "default_model: [unclosed\n"))


def test_unknown_top_level_field_is_diagnostic(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, "modle: openai/gpt-4o\n"))
    assert "modle" in str(excinfo.value)


def test_default_path_is_intelliagent_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_config(
        tmp_path,
        "default_model: local/model\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        "    api: http://127.0.0.1:8000/v1\n"
        "    models:\n"
        "      model: {}\n",
    )
    monkeypatch.chdir(tmp_path)
    assert load_config().default_model == "local/model"


# ============================================================================
# 环境变量插值（{env:NAME} / {env:NAME:default}，需加引号）
# ============================================================================


def test_interpolate_env_handles_mixed_text_and_colon_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T52_HOST", "localhost")
    monkeypatch.delenv("T52_URL", raising=False)
    assert interpolate_env("http://{env:T52_HOST}:8080") == "http://localhost:8080"
    assert interpolate_env("{env:T52_URL:postgresql://localhost:5432/db}") == "postgresql://localhost:5432/db"


def test_interpolates_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T52_HOST", "http://127.0.0.1:9000")
    content = (
        "default_model: local/model\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        '    api: "{env:T52_HOST}"\n'
        "    models:\n"
        "      model: {}\n"
    )
    config = load_config(_write_config(tmp_path, content))
    assert config.providers["local"].api == "http://127.0.0.1:9000"


def test_interpolation_uses_default_when_var_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("T52_MISSING", raising=False)
    content = (
        "default_model: local/model\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        '    api: "{env:T52_MISSING:http://fallback/v1}"\n'
        "    models:\n"
        "      model: {}\n"
    )
    config = load_config(_write_config(tmp_path, content))
    assert config.providers["local"].api == "http://fallback/v1"


def test_missing_var_without_default_raises_config_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("T52_MISSING", raising=False)
    content = (
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        '    api: "{env:T52_MISSING}"\n'
        "    models:\n"
        "      model: {}\n"
    )
    with pytest.raises(ConfigError, match="T52_MISSING"):
        load_config(_write_config(tmp_path, content))


def test_missing_var_error_names_plugin_and_field(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("T52_TOKEN", raising=False)
    content = 'plugins:\n  mcp:\n    config:\n      token: "{env:T52_TOKEN}"\n'
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, content))
    message = str(excinfo.value)
    assert "plugins.mcp.config.token" in message
    assert "T52_TOKEN" in message


def test_interpolation_applies_to_nested_plugin_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("T52_ROOT", "/srv/skills")
    content = 'plugins:\n  skill:\n    config:\n      project_paths:\n        - "{env:T52_ROOT}/project"\n'
    config = load_config(_write_config(tmp_path, content))
    assert config.plugins["skill"].config["project_paths"] == ["/srv/skills/project"]


# ============================================================================
# plugins 段（enabled + 每插件配置）
# ============================================================================


def test_plugins_section_reads_enabled_and_config(tmp_path: Path) -> None:
    content = (
        "plugins:\n"
        "  skill:\n"
        "    enabled: false\n"
        "    config:\n"
        "      project_paths:\n"
        "        - .agents/skills\n"
        "  mcp:\n"
        "    enabled: true\n"
    )
    config = load_config(_write_config(tmp_path, content))
    assert config.plugins["skill"].enabled is False
    assert config.plugins["skill"].config == {"project_paths": [".agents/skills"]}
    assert config.plugins["mcp"].enabled is True
    assert config.plugins["mcp"].config == {}


def test_plugin_defaults_enabled_true_and_empty_config(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, "plugins:\n  memory: {}\n"))
    plugin = config.plugins["memory"]
    assert plugin.enabled is True
    assert plugin.config == {}


def test_plugin_entry_must_be_mapping(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, "plugins:\n  mcp: true\n"))
    message = str(excinfo.value)
    assert "mcp" in message
    assert "plugins" in message


# ============================================================================
# 非法配置的诊断错误（含插件名与字段名）
# ============================================================================


def test_invalid_plugin_field_error_names_plugin_and_field(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, "plugins:\n  mcp:\n    enabled: sometimes\n"))
    message = str(excinfo.value)
    assert "mcp" in message
    assert "enabled" in message


def test_unknown_plugin_field_error_names_plugin_and_field(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, "plugins:\n  skill:\n    enabeld: true\n"))
    message = str(excinfo.value)
    assert "skill" in message
    assert "enabeld" in message


def test_invalid_top_level_field_error_names_field(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, "max_steps: many\n"))
    assert "max_steps" in str(excinfo.value)


def test_invalid_workspace_field_error_names_field(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, "workspace:\n  dir: 123\n"))
    message = str(excinfo.value)
    assert "workspace" in message
    assert "dir" in message


# ============================================================================
# 旧 intelliagent.json 不被读取
# ============================================================================


def test_yaml_wins_when_old_json_also_present(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "default_model: local/model\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        "    api: http://x/v1\n"
        "    models:\n"
        "      model: {}\n",
    )
    _write_config(tmp_path, '{"model": "from-json"}', name="intelliagent.json")
    assert load_config(tmp_path / "intelliagent.yaml").default_model == "local/model"


def test_old_json_is_not_read_as_fallback(tmp_path: Path) -> None:
    _write_config(tmp_path, '{"model": "from-json"}', name="intelliagent.json")
    with pytest.raises(ConfigError, match="intelliagent.yaml"):
        load_config(tmp_path / "intelliagent.yaml")


class TestStrictYamlLoader:
    """YAML 静默陷阱防线（PR #66 审查 Spec 轴 medium）：重复键与布尔化键必须显式报错。"""

    def test_duplicate_key_rejected(self, tmp_path: Path) -> None:
        config_file = tmp_path / "intelliagent.yaml"
        config_file.write_text("default_model: a/one\ndefault_model: b/two\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="重复的键"):
            load_config(config_file)

    def test_booleanified_key_rejected(self, tmp_path: Path) -> None:
        config_file = tmp_path / "intelliagent.yaml"
        config_file.write_text("plugins:\n  on:\n    enabled: true\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="键必须是字符串"):
            load_config(config_file)

    def test_quoted_on_key_accepted(self, tmp_path: Path) -> None:
        config_file = tmp_path / "intelliagent.yaml"
        config_file.write_text('plugins:\n  "on":\n    enabled: true\n', encoding="utf-8")
        config = load_config(config_file)
        assert "on" in config.plugins


# ============================================================================
# Provider 配置（ADR 0011）
# ============================================================================


def test_old_model_field_gets_migration_message(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, "model: openai/gpt-4o\n"))
    message = str(excinfo.value)
    assert "default_model" in message
    assert "providers" in message


def test_unknown_default_model_provider_is_diagnostic(tmp_path: Path) -> None:
    content = "default_model: nope/model\nproviders: {}\n"
    with pytest.raises(ConfigError, match="未知 provider"):
        load_config(_write_config(tmp_path, content))


def test_unknown_default_model_model_is_diagnostic(tmp_path: Path) -> None:
    content = (
        "default_model: local/nope\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        "    api: http://x/v1\n"
        "    models:\n"
        "      model: {}\n"
    )
    with pytest.raises(ConfigError, match="没有模型"):
        load_config(_write_config(tmp_path, content))


def test_openai_compatible_requires_api(tmp_path: Path) -> None:
    content = "providers:\n  local:\n    type: openai-compatible\n    models:\n      model: {}\n"
    with pytest.raises(ConfigError, match="requires api"):
        load_config(_write_config(tmp_path, content))


def test_model_metadata_is_declared_with_defaults(tmp_path: Path) -> None:
    content = (
        "default_model: local/model\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        "    api: http://x/v1\n"
        "    env: [LOCAL_KEY]\n"
        "    models:\n"
        "      model:\n"
        "        reasoning: true\n"
        "        reasoning_level: [low, high]\n"
        "        tool_call: false\n"
        "        modalities:\n"
        "          input: [text, image]\n"
        "          output: [text]\n"
        "        limit:\n"
        "          context: 1000\n"
        "          output: 200\n"
        "        cost:\n"
        "          input: 0.1\n"
        "          output: 0.2\n"
    )
    config = load_config(_write_config(tmp_path, content))
    model = config.providers["local"].models["model"]
    assert model.tool_call is False
    assert model.reasoning is True
    assert model.reasoning_level == ["low", "high"]
    assert model.modalities.input == ["text", "image"]
    assert model.limit.context == 1000
    assert model.limit.output == 200
    assert model.cost is not None and model.cost.output == 0.2
    assert model.id is None


def test_unknown_model_field_is_diagnostic(tmp_path: Path) -> None:
    content = (
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        "    api: http://x/v1\n"
        "    models:\n"
        "      model:\n"
        "        enabeld: true\n"
    )
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, content))
    assert "enabeld" in str(excinfo.value)


def test_plaintext_api_key_is_rejected(tmp_path: Path) -> None:
    content = (
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        "    api: http://x/v1\n"
        "    api_key: sk-secret\n"
        "    models:\n"
        "      model: {}\n"
    )
    with pytest.raises(ConfigError) as excinfo:
        load_config(_write_config(tmp_path, content))
    assert "api_key" in str(excinfo.value)

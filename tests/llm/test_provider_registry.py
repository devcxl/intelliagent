"""ModelRegistry：Model Ref 解析、env 顺序、默认端点与可诊断错误。"""

from __future__ import annotations

import pytest

from src.llm.provider_registry import ModelRegistry, ModelSettings, ProviderSettings


def _registry() -> ModelRegistry:
    return ModelRegistry(
        {
            "local": ProviderSettings(
                protocol="openai-compatible",
                api_base="http://127.0.0.1:8000/v1",
                models={"model": ModelSettings(wire_model="wire-model", max_output_tokens=64)},
            ),
            "openai": ProviderSettings(
                protocol="openai",
                models={"gpt": ModelSettings(wire_model="gpt-4o")},
            ),
            "org": ProviderSettings(
                protocol="openai-compatible",
                api_base="http://org/v1",
                env=("ORG_KEY", "FALLBACK_KEY"),
                models={"m": ModelSettings(wire_model="org/model-with-slash")},
            ),
        }
    )


def test_resolves_target_with_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    target = _registry().resolve("local/model")

    assert target.provider == "local"
    assert target.wire_model == "wire-model"
    assert target.api_base == "http://127.0.0.1:8000/v1"
    assert target.api_key is None
    assert target.max_output_tokens == 64


def test_uses_default_openai_endpoint_and_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    target = _registry().resolve("openai/gpt")

    assert target.api_base == "https://api.openai.com/v1"
    assert target.api_key == "sk-test"


def test_env_list_takes_first_non_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FALLBACK_KEY", "fallback")
    monkeypatch.delenv("ORG_KEY", raising=False)
    target = _registry().resolve("org/m")
    assert target.api_key == "fallback"

    monkeypatch.setenv("ORG_KEY", "primary")
    assert _registry().resolve("org/m").api_key == "primary"


def test_model_id_can_contain_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORG_KEY", "k")
    registry = ModelRegistry(
        {
            "p": ProviderSettings(
                protocol="openai-compatible",
                api_base="http://p/v1",
                models={"meta/llama": ModelSettings(wire_model="meta/llama")},
            )
        }
    )
    assert registry.resolve("p/meta/llama").model_id == "meta/llama"


def test_unknown_provider_and_model_are_diagnostic() -> None:
    with pytest.raises(ValueError, match="未知 provider"):
        _registry().resolve("nope/model")
    with pytest.raises(ValueError, match="没有模型"):
        _registry().resolve("local/nope")
    with pytest.raises(ValueError, match="provider/model-id"):
        _registry().resolve("no-slash")


def test_missing_key_for_openai_is_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        _registry().resolve("openai/gpt")

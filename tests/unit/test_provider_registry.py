#!/usr/bin/env python3
"""ProviderRegistry 单元测试。"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config.provider_registry import CACHE_FILE, ProviderRegistry

SAMPLE_DATA = {
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "npm": "@ai-sdk/openai",
        "models": {
            "gpt-4o": {
                "id": "gpt-4o",
                "name": "GPT-4o",
                "limit": {"context": 128000, "output": 16384},
            },
            "gpt-4o-mini": {
                "id": "gpt-4o-mini",
                "name": "GPT-4o Mini",
                "limit": {"context": 128000, "output": 16384},
            },
        },
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "npm": "@ai-sdk/deepseek",
        "models": {
            "deepseek-v4-flash": {
                "id": "deepseek-v4-flash",
                "name": "DeepSeek V4 Flash",
                "limit": {"context": 65536, "output": 8192},
            },
        },
    },
}

SAMPLE_DATA_NO_LIMIT = {
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "npm": "@ai-sdk/openai",
        "models": {
            "gpt-4o": {
                "id": "gpt-4o",
                "name": "GPT-4o",
            },
        },
    },
}


@pytest.fixture(autouse=True)
def _clear_registry():
    ProviderRegistry.clear_cache()
    yield
    ProviderRegistry.clear_cache()


class TestProviderRegistryLoad:
    def test_load_from_cache(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            providers = ProviderRegistry.load()

        assert "openai" in providers
        assert providers["openai"].id == "openai"

    def test_load_from_remote_when_cache_missing(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        with (
            patch("src.config.provider_registry.CACHE_FILE", cache_file),
            patch("src.config.provider_registry.urllib.request.urlopen") as mock_urlopen,
        ):
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.read.return_value = json.dumps(SAMPLE_DATA).encode("utf-8")

            providers = ProviderRegistry.load()

        assert "deepseek" in providers
        assert cache_file.exists()
        cached = json.loads(cache_file.read_text())
        assert cached["deepseek"]["models"]["deepseek-v4-flash"]["limit"]["context"] == 65536

    def test_force_refresh_ignores_cache(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps({}))
        with (
            patch("src.config.provider_registry.CACHE_FILE", cache_file),
            patch("src.config.provider_registry.urllib.request.urlopen") as mock_urlopen,
        ):
            mock_resp = mock_urlopen.return_value.__enter__.return_value
            mock_resp.read.return_value = json.dumps(SAMPLE_DATA).encode("utf-8")

            providers = ProviderRegistry.load(force_refresh=True)

        assert "openai" in providers
        assert "deepseek" in providers

    def test_memory_cache_avoids_remote(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            providers1 = ProviderRegistry.load()
            providers2 = ProviderRegistry.load()

        assert providers1 is providers2


class TestGetModelContextLimit:
    def test_returns_context_from_registry(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            result = ProviderRegistry.get_model_context_limit("deepseek", "deepseek-v4-flash")

        assert result == 65536

    def test_returns_none_for_unknown_provider(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            result = ProviderRegistry.get_model_context_limit("nonexistent", "gpt-4o")

        assert result is None

    def test_returns_none_for_unknown_model(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            result = ProviderRegistry.get_model_context_limit("openai", "gpt-5")

        assert result is None

    def test_returns_none_when_model_has_no_limit(self, tmp_path):
        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA_NO_LIMIT))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            result = ProviderRegistry.get_model_context_limit("openai", "gpt-4o")

        assert result is None


class TestGetModelContextLimitIntegration:
    def test_user_config_overrides_registry(self, tmp_path):
        from src.config.unified_config import UnifiedConfig

        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            config = UnifiedConfig.model_validate(
                {
                    "model": "deepseek/deepseek-v4-flash",
                    "provider": {
                        "deepseek": {
                            "models": {
                                "deepseek-v4-flash": {
                                    "limit": {"context": 99999},
                                },
                            },
                        },
                    },
                }
            )
            result = config.get_model_context_limit()

        assert result == 99999

    def test_falls_back_to_registry_when_no_user_config(self, tmp_path):
        from src.config.unified_config import UnifiedConfig

        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            config = UnifiedConfig.model_validate(
                {
                    "model": "deepseek/deepseek-v4-flash",
                }
            )
            result = config.get_model_context_limit()

        assert result == 65536

    def test_returns_none_when_not_found_anywhere(self, tmp_path):
        from src.config.unified_config import UnifiedConfig

        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            config = UnifiedConfig.model_validate(
                {
                    "model": "nonexistent/nope",
                }
            )
            result = config.get_model_context_limit()

        assert result is None

    def test_user_config_override_to_none_still_falls_back(self, tmp_path):
        from src.config.unified_config import UnifiedConfig

        cache_file = tmp_path / "providers.json"
        cache_file.write_text(json.dumps(SAMPLE_DATA))
        with patch("src.config.provider_registry.CACHE_FILE", cache_file):
            config = UnifiedConfig.model_validate(
                {
                    "model": "deepseek/deepseek-v4-flash",
                    "provider": {
                        "deepseek": {
                            "models": {
                                "deepseek-v4-flash": {},
                            },
                        },
                    },
                }
            )
            result = config.get_model_context_limit()

        assert result == 65536

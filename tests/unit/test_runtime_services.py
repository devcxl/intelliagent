#!/usr/bin/env python3
"""PR2 runtime / service 测试。"""

from typing import Any, cast

import src.runtime.engine_factory as engine_factory_module
from src.config.unified_config import UnifiedConfig
from src.runtime import EngineFactory, create_default_llm_client, create_default_permission_engine
from src.tools.registry import ToolRegistry


def test_engine_factory_reuses_cached_llm_provider(monkeypatch):
    created_llm_clients = []
    created_engines = []

    class FakeLLMClient:
        def __init__(self, api_key=None, base_url=None, model=None):
            self.api_key = api_key
            self.base_url = base_url
            self.model = model
            created_llm_clients.append(self)

    class FakeReactEngine:
        def __init__(self, llm_client=None, tools_registry=None, memory=None, max_tokens=128000, **kwargs):
            self.llm_client = llm_client
            self.tools = tools_registry
            self.memory = memory
            self.max_tokens = max_tokens
            created_engines.append(self)

    monkeypatch.setattr(engine_factory_module, "ReactEngine", FakeReactEngine)

    cached_llm_client = None

    def get_llm_client():
        nonlocal cached_llm_client
        if cached_llm_client is None:
            cached_llm_client = FakeLLMClient(
                api_key="test-key",
                model="test-model",
            )
        return cached_llm_client

    factory = EngineFactory(
        config=UnifiedConfig(),
        llm_client_provider=cast(Any, get_llm_client),
        permission_engine_factory=cast(Any, lambda: None),
        permission_callback_factory=cast(Any, lambda: None),
        tool_registry=ToolRegistry(),
        skill_registry=None,
    )

    first_engine = cast(Any, factory.create())
    second_engine = cast(Any, factory.create())

    assert len(created_llm_clients) == 1
    assert len(created_engines) == 2
    assert first_engine.llm_client is second_engine.llm_client


def test_engine_factory_keeps_default_token_limit(monkeypatch):
    created_engines = []

    class FakeLLMClient:
        def __init__(self, api_key=None, base_url=None, model=None):
            pass

    class FakePermissionEngine:
        pass

    class FakePermissionCallback:
        pass

    class FakeReactEngine:
        def __init__(self, llm_client=None, context_limit=None, **kwargs):
            self.context_limit = context_limit or 128000
            self.permission_engine = kwargs.get("permission_engine")
            self.permission_callback = kwargs.get("permission_callback")
            created_engines.append(self)

    monkeypatch.setattr(engine_factory_module, "ReactEngine", FakeReactEngine)

    factory = EngineFactory(
        config=UnifiedConfig(),
        llm_client_provider=cast(
            Any,
            lambda: FakeLLMClient(
                api_key="test-key",
                model="test-model",
            ),
        ),
        permission_engine_factory=cast(Any, FakePermissionEngine),
        permission_callback_factory=cast(Any, FakePermissionCallback),
        tool_registry=ToolRegistry(),
        skill_registry=None,
    )

    engine = cast(Any, factory.create())

    assert created_engines == [engine]
    assert engine.context_limit == 128000
    assert engine.permission_engine is not None
    assert engine.permission_callback is not None


# ============================================================================
# 新增：默认 runtime factory 从 UnifiedConfig 构造
# ============================================================================


def test_agent_runtime_from_unified_config_uses_provider_fields(monkeypatch):
    """默认 LLM 工厂应使用 UnifiedConfig 的 provider 字段。"""
    import src.llm.llm_client as llm_client_module

    captured_kwargs = {}

    class FakeLLMClient:
        def __init__(self, api_key=None, base_url=None, model=None):
            captured_kwargs["api_key"] = api_key
            captured_kwargs["base_url"] = base_url
            captured_kwargs["model"] = model

    monkeypatch.setattr(llm_client_module, "LLMClient", FakeLLMClient)

    config = UnifiedConfig.model_validate(
        {
            "model": "unified-model",
            "provider": {
                "openai": {
                    "options": {
                        "apiKey": "sk-unified",
                        "baseURL": "https://unified.example.com",
                    },
                },
            },
        }
    )

    create_default_llm_client(config)

    assert captured_kwargs["api_key"] == "sk-unified"
    assert captured_kwargs["base_url"] == "https://unified.example.com"
    assert captured_kwargs["model"] == "unified-model"


def test_agent_runtime_from_unified_config_permission_engine(monkeypatch):
    """默认权限引擎工厂应使用 permissions 子模型。"""
    from src.permission import PermissionEngine

    config = UnifiedConfig.model_validate(
        {
            "permissions": {
                "rules": [
                    {"pattern": "run_shell", "action": "deny"},
                ],
            },
        }
    )

    engine = create_default_permission_engine(config)

    assert isinstance(engine, PermissionEngine)
    assert len(engine.rules) == 1
    assert engine.rules[0] == ("run_shell", "deny")


def test_agent_runtime_from_unified_config_workspace(monkeypatch):
    """默认权限引擎工厂应从配置读取 workspace。"""
    from pathlib import Path

    from src.permission import PermissionEngine

    config = UnifiedConfig.model_validate(
        {
            "workspace": {"dir": "/tmp/custom-ws"},
        }
    )

    engine = create_default_permission_engine(config)

    assert isinstance(engine, PermissionEngine)
    assert engine._path_policy.workspace == Path("/tmp/custom-ws")


# ============================================================================
# 新增：test_settings.py 已覆盖 backward compat
# ============================================================================

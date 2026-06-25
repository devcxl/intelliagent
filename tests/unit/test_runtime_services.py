#!/usr/bin/env python3
"""PR2 runtime / service 测试。"""

import src.runtime.agent_runtime as agent_runtime_module
from src.config.unified_config import UnifiedConfig
from src.runtime import AgentRuntime


def test_agent_runtime_reuses_shared_components(monkeypatch):
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

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", FakeReactEngine)

    runtime = AgentRuntime(
        llm_client_factory=lambda: FakeLLMClient(
            api_key="test-key",
            model="test-model",
        ),
    )

    first_llm = runtime.get_llm_client()
    second_llm = runtime.get_llm_client()
    import asyncio

    first_engine = asyncio.run(runtime.create_engine())
    second_engine = asyncio.run(runtime.create_engine())

    assert first_llm is second_llm
    assert len(created_llm_clients) == 1
    assert len(created_engines) == 2
    assert first_engine.llm_client is second_engine.llm_client


def test_agent_runtime_create_engine_keeps_default_token_limit(monkeypatch):
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

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", FakeReactEngine)

    import asyncio

    engine = asyncio.run(
        AgentRuntime(
            llm_client_factory=FakeLLMClient,
            permission_engine_factory=FakePermissionEngine,
            permission_callback_factory=FakePermissionCallback,
        ).create_engine()
    )

    assert created_engines == [engine]
    assert engine.context_limit == 128000
    assert engine.permission_engine is not None
    assert engine.permission_callback is not None


# ============================================================================
# 新增：AgentRuntime 从 UnifiedConfig 构造
# ============================================================================


def test_agent_runtime_from_unified_config_uses_provider_fields(monkeypatch):
    """AgentRuntime 从 UnifiedConfig 构造时，默认 LLM 工厂应使用 provider 字段。"""
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

    runtime = AgentRuntime(config=config)
    runtime._default_llm_client_factory()

    assert captured_kwargs["api_key"] == "sk-unified"
    assert captured_kwargs["base_url"] == "https://unified.example.com"
    assert captured_kwargs["model"] == "unified-model"


def test_agent_runtime_from_unified_config_permission_engine(monkeypatch):
    """AgentRuntime 从 UnifiedConfig 构造时，权限引擎应使用 permissions 子模型。"""
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

    runtime = AgentRuntime(config=config)
    engine = runtime._default_permission_engine_factory()

    assert isinstance(engine, PermissionEngine)
    assert len(engine.rules) == 1
    assert engine.rules[0] == ("run_shell", "deny")


def test_agent_runtime_from_unified_config_workspace(monkeypatch):
    """AgentRuntime 从 UnifiedConfig 构造时，workspace 应从配置读取。"""
    from pathlib import Path

    from src.permission import PermissionEngine

    config = UnifiedConfig.model_validate(
        {
            "workspace": {"dir": "/tmp/custom-ws"},
        }
    )

    runtime = AgentRuntime(config=config)
    engine = runtime._default_permission_engine_factory()

    assert isinstance(engine, PermissionEngine)
    assert engine._workspace == Path("/tmp/custom-ws")


# ============================================================================
# 新增：test_settings.py 已覆盖 backward compat
# ============================================================================

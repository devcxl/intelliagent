#!/usr/bin/env python3
"""PR2 runtime / service 测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import src.runtime.agent_runtime as agent_runtime_module
from src.config.unified_config import UnifiedConfig
from src.runtime import AgentRuntime, RunService


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
    first_engine = runtime.create_engine()
    second_engine = runtime.create_engine()

    assert first_llm is second_llm
    assert len(created_llm_clients) == 1
    assert len(created_engines) == 2
    assert first_engine.llm_client is second_engine.llm_client


def test_run_service_sync_wrapper_uses_async_entry(monkeypatch):
    runtime = Mock()
    service = RunService(runtime, db_manager=Mock())

    async def fake_run_task_async(**kwargs):
        return {"success": True, "summary": "ok", "iterations": kwargs["max_iterations"]}

    monkeypatch.setattr(service, "run_task_async", fake_run_task_async)

    result = service.run_task(task="测试任务", max_iterations=3)

    assert result["success"] is True
    assert result["iterations"] == 3


async def test_run_service_run_task_async_uses_engine_run():
    engine = Mock(spec=["run", "iter_steps"])
    engine.run = AsyncMock(return_value={"success": True, "summary": "ok", "num_turns": 1})

    runtime = Mock()
    runtime.create_engine.return_value = engine
    service = RunService(runtime, db_manager=Mock())

    result = await service.run_task_async(task="测试任务", max_iterations=3)

    assert result["success"] is True
    runtime.create_engine.assert_called_once_with(
        api_key=None,
        model=None,
        max_iterations=3,
    )
    engine.run.assert_awaited_once_with(
        "测试任务",
        max_iterations=3,
        history_context=None,
    )


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
        def __init__(self, llm_client=None, max_tokens=128000, **kwargs):
            self.max_tokens = max_tokens
            self.max_iterations = kwargs.get("max_iterations")
            self.permission_engine = kwargs.get("permission_engine")
            self.permission_callback = kwargs.get("permission_callback")
            created_engines.append(self)

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", FakeReactEngine)

    settings = SimpleNamespace(
        OPENAI_API_KEY="test-key",
        OPENAI_API_BASE=None,
        OPENAI_MODEL="test-model",
    )

    engine = AgentRuntime(
        llm_client_factory=FakeLLMClient,
        permission_engine_factory=FakePermissionEngine,
        permission_callback_factory=FakePermissionCallback,
    ).create_engine(max_iterations=3)

    assert created_engines == [engine]
    assert engine.max_tokens == 128000
    assert engine.max_iterations == 3
    assert engine.permission_engine is not None
    assert engine.permission_callback is not None


async def test_run_service_streams_steps_from_engine():
    class FakeEngine:
        async def iter_steps(self, task, max_iterations=None, **kwargs):
            assert max_iterations == 2
            yield {
                "type": "thought",
                "iteration": 1,
                "data": {"reasoning": "先读取文件", "is_complete": False},
            }
            yield {
                "type": "action",
                "iteration": 1,
                "data": {"tool": "read_file", "args": {"path": "a.txt"}},
            }
            yield {
                "type": "observation",
                "iteration": 1,
                "data": {"status": "ok", "result": "content"},
            }
            yield {
                "type": "answer",
                "iteration": 2,
                "data": {"answer": "done"},
            }

    runtime = Mock()
    runtime.create_engine.return_value = FakeEngine()
    service = RunService(runtime, db_manager=Mock())

    steps = []
    async for step in service.run_task_stream(task="测试任务", max_iterations=2):
        steps.append(step)

    assert [step["type"] for step in steps] == [
        "thought",
        "action",
        "observation",
        "answer",
    ]


# ============================================================================
# 新增：AgentRuntime 从 UnifiedConfig 构造
# ============================================================================


def test_agent_runtime_from_unified_config_uses_llm_fields(monkeypatch):
    """AgentRuntime 从 UnifiedConfig 构造时，默认 LLM 工厂应使用 llm 子模型字段。"""
    import src.llm.llm_client as llm_client_module

    captured_kwargs = {}

    class FakeLLMClient:
        def __init__(self, api_key=None, base_url=None, model=None):
            captured_kwargs["api_key"] = api_key
            captured_kwargs["base_url"] = base_url
            captured_kwargs["model"] = model

    monkeypatch.setattr(llm_client_module, "LLMClient", FakeLLMClient)

    config = UnifiedConfig.model_validate({
        "llm": {
            "api_key": "sk-unified",
            "base_url": "https://unified.example.com",
            "model": "unified-model",
        },
    })

    runtime = AgentRuntime(config=config)
    runtime._default_llm_client_factory()

    assert captured_kwargs["api_key"] == "sk-unified"
    assert captured_kwargs["base_url"] == "https://unified.example.com"
    assert captured_kwargs["model"] == "unified-model"


def test_agent_runtime_from_unified_config_permission_engine(monkeypatch):
    """AgentRuntime 从 UnifiedConfig 构造时，权限引擎应使用 permissions 子模型。"""
    from src.core.permission_engine import PermissionEngine

    config = UnifiedConfig.model_validate({
        "permissions": {
            "rules": [
                {"tool": "run_shell", "action": "deny", "conditions": {}},
            ],
        },
    })

    runtime = AgentRuntime(config=config)
    engine = runtime._default_permission_engine_factory()

    assert isinstance(engine, PermissionEngine)
    assert len(engine.rules) == 1
    assert engine.rules[0].tool == "run_shell"
    assert engine.rules[0].action.value == "deny"


def test_agent_runtime_from_unified_config_workspace(monkeypatch):
    """AgentRuntime 从 UnifiedConfig 构造时，workspace 应从配置读取。"""
    from pathlib import Path

    from src.core.permission_engine import PermissionEngine

    config = UnifiedConfig.model_validate({
        "workspace": {"dir": "/tmp/custom-ws"},
    })

    runtime = AgentRuntime(config=config)
    engine = runtime._default_permission_engine_factory()

    assert isinstance(engine, PermissionEngine)
    assert engine._workspace == Path("/tmp/custom-ws")


# ============================================================================
# 新增：test_settings.py 已覆盖 backward compat
# ============================================================================

#!/usr/bin/env python3
"""PR2 runtime / service 测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import src.runtime.agent_runtime as agent_runtime_module
from src.runtime import AgentRuntime
from src.services import RunService, SessionService


def test_agent_runtime_reuses_shared_components(monkeypatch):
    created_llm_clients = []
    created_tool_registries = []
    created_engines = []

    class FakeLLMClient:
        def __init__(self, api_key=None, base_url=None, model=None):
            self.api_key = api_key
            self.base_url = base_url
            self.model = model
            created_llm_clients.append(self)

    class FakeToolRegistry:
        def __init__(self):
            created_tool_registries.append(self)

    class FakeMemory:
        def __init__(self, experience_file=None):
            self.experience_file = experience_file

    class FakeContextManager:
        pass

    class FakeReactEngine:
        def __init__(self, llm_client, tools, memory, context, max_iterations):
            self.llm_client = llm_client
            self.tools = tools
            self.memory = memory
            self.context = context
            self.max_iterations = max_iterations
            created_engines.append(self)

    monkeypatch.setattr(agent_runtime_module, "LLMClient", FakeLLMClient)
    monkeypatch.setattr(agent_runtime_module, "ToolRegistry", FakeToolRegistry)
    monkeypatch.setattr(agent_runtime_module, "Memory", FakeMemory)
    monkeypatch.setattr(agent_runtime_module, "ContextManager", FakeContextManager)
    monkeypatch.setattr(agent_runtime_module, "ReactEngine", FakeReactEngine)

    settings = SimpleNamespace(
        OPENAI_API_KEY="test-key",
        OPENAI_API_BASE=None,
        OPENAI_MODEL="test-model",
        MAX_PDCA_CYCLES=3,
        EXPERIENCE_FILE="experiences.json",
    )
    runtime = AgentRuntime(settings=settings)

    first_llm = runtime.get_llm_client()
    second_llm = runtime.get_llm_client()
    first_engine = runtime.create_engine()
    second_engine = runtime.create_engine()

    assert first_llm is second_llm
    assert len(created_llm_clients) == 1
    assert len(created_tool_registries) == 2
    assert len(created_engines) == 2
    assert first_engine.tools is not second_engine.tools
    assert first_engine.memory is not second_engine.memory
    assert first_engine.context is not second_engine.context
    assert first_engine.llm_client is second_engine.llm_client


async def test_session_service_delegates_to_database_manager():
    db_manager = Mock()
    db_manager.get_all_sessions = AsyncMock(return_value=[{"id": "s1"}])
    service = SessionService(db_manager)

    result = await service.get_all_sessions()

    assert result == [{"id": "s1"}]
    db_manager.get_all_sessions.assert_awaited_once()


def test_run_service_sync_wrapper_uses_async_entry(monkeypatch):
    runtime = Mock()
    service = RunService(runtime, session_manager=Mock())

    async def fake_run_task_async(**kwargs):
        return {"success": True, "summary": "ok", "iterations": kwargs["max_iterations"]}

    monkeypatch.setattr(service, "run_task_async", fake_run_task_async)

    result = service.run_task(task="测试任务", max_iterations=3)

    assert result["success"] is True
    assert result["iterations"] == 3


async def test_run_service_run_task_async_uses_engine_run_async():
    engine = Mock()
    engine.run_async = AsyncMock(return_value={"success": True, "summary": "ok", "iterations": 1})

    runtime = Mock()
    runtime.create_engine.return_value = engine
    service = RunService(runtime, session_manager=Mock())

    result = await service.run_task_async(task="测试任务", max_iterations=3)

    assert result["success"] is True
    runtime.create_engine.assert_called_once_with(
        api_key=None,
        model=None,
        max_iterations=3,
    )
    engine.run_async.assert_awaited_once_with("测试任务", max_iterations=3)


async def test_run_service_streams_steps_from_engine():
    class FakeEngine:
        async def iter_steps(self, task, max_iterations=None, **kwargs):
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
    service = RunService(runtime, session_manager=Mock())

    steps = []
    async for step in service.run_task_stream(task="测试任务", max_iterations=2):
        steps.append(step)

    assert [step["type"] for step in steps] == [
        "thought",
        "action",
        "observation",
        "answer",
    ]

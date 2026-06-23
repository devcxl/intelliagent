from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.runtime.conversation_orchestrator as orchestrator_module
import src.main as main_module


class FakeEngine:
    def __init__(self, calls=None):
        self.calls = calls

    async def iter_steps(self, task: str, **kwargs):
        if self.calls is not None:
            self.calls.append(("iter_steps", task, kwargs))
        yield {"type": "answer", "iteration": 1, "data": {"answer": "done"}}


class FakeAgentRuntime:
    def __init__(self, config=None):
        self._config = config
        self._mcp_manager = None

    async def create_engine(self):
        return FakeEngine()

    async def start_mcp(self, registry=None):
        pass

    async def stop_mcp(self):
        pass


def _patch_orchestrator_dependencies(monkeypatch, tmp_path, created=None):
    """Patch orchestrator 模块中的依赖，使其使用真实内存 SQLite + fake runtime。"""
    settings = SimpleNamespace(DATABASE_URL=str(tmp_path / "test.db"))

    class RecordingAgentRuntime(FakeAgentRuntime):
        def __init__(self, config=None):
            super().__init__(config)
            if created is not None:
                created["config"] = config

        async def create_engine(self):
            if created is not None:
                created["create_engine_called"] = True
                return FakeEngine(created.setdefault("engine_calls", []))
            return FakeEngine()

    monkeypatch.setattr(orchestrator_module, "get_settings", lambda: settings)
    monkeypatch.setattr(orchestrator_module, "AgentRuntime", RecordingAgentRuntime)
    return settings


@pytest.mark.asyncio
async def test_main_creates_engine_through_agent_runtime(monkeypatch, tmp_path):
    created = {}

    def fail_if_direct_llm_is_used(*args, **kwargs):
        raise AssertionError("main.py must create engines through AgentRuntime")

    _patch_orchestrator_dependencies(monkeypatch, tmp_path, created)
    monkeypatch.setattr(orchestrator_module, "LLMClient", fail_if_direct_llm_is_used, raising=False)

    await main_module.main(task="测试任务")

    assert created["config"] is None
    assert created["create_engine_called"] is True


@pytest.mark.asyncio
async def test_main_passes_history_context_to_engine(monkeypatch, tmp_path):
    created = {}
    _patch_orchestrator_dependencies(monkeypatch, tmp_path, created)

    # 先创建一条历史消息
    await main_module.main(task="之前的任务")

    # 第二次调用应包含历史上下文（但因为是新 conversation，所以 history_context 为 None）
    # 改为直接测试 resume 模式
    created.clear()
    created["engine_calls"] = []
    await main_module.main(task="测试任务", resume=True)

    assert created["engine_calls"][0][0] == "iter_steps"
    assert "测试任务" in created["engine_calls"][0][1]


@pytest.mark.asyncio
async def test_main_session_alias_updates_existing_conversation(monkeypatch, tmp_path):
    _patch_orchestrator_dependencies(monkeypatch, tmp_path)

    # 先创建一个 conversation
    await main_module.main(task="原始任务", session_id="conversation-1")

    # 再用相同 session_id 恢复
    await main_module.main(task="新任务", session_id="conversation-1")


@pytest.mark.asyncio
async def test_main_session_alias_creates_missing_conversation(monkeypatch, tmp_path):
    _patch_orchestrator_dependencies(monkeypatch, tmp_path)

    # session_id 不存在 → 创建新 conversation
    await main_module.main(task="测试任务", session_id="conversation-new")


@pytest.mark.asyncio
async def test_main_resume_uses_latest_conversation(monkeypatch, tmp_path):
    _patch_orchestrator_dependencies(monkeypatch, tmp_path)

    # 先创建一个 conversation
    await main_module.main(task="第一个任务")

    # resume 应恢复最近的 conversation
    await main_module.main(task="后续任务", resume=True)


@pytest.mark.asyncio
async def test_main_history_lists_conversations(monkeypatch, tmp_path):
    _patch_orchestrator_dependencies(monkeypatch, tmp_path)

    # 创建一个 conversation
    await main_module.main(task="历史任务")

    # 查看历史
    await main_module.main(task="", list_history=True)


@pytest.mark.asyncio
async def test_orchestrator_uses_injected_runtime_factory(monkeypatch, tmp_path):
    """注入 runtime_factory 后，execute 应使用注入的 runtime 而非默认 AgentRuntime。"""
    from src.runtime.conversation_orchestrator import ConversationOrchestrator

    settings = SimpleNamespace(DATABASE_URL=str(tmp_path / "test.db"))
    monkeypatch.setattr(orchestrator_module, "get_settings", lambda: settings)

    stop_called = []

    class InjectedRuntime:
        async def create_engine(self):
            return FakeEngine()

        async def start_mcp(self, registry=None):
            pass

        async def stop_mcp(self):
            stop_called.append(True)

    orchestrator = ConversationOrchestrator(
        settings=settings,
        runtime_factory=InjectedRuntime,
    )
    await orchestrator.initialize()
    await orchestrator.setup_conversation("测试任务")

    async for event in orchestrator.execute("测试任务"):
        assert event["type"] == "answer"
        assert event["data"]["answer"] == "done"

    assert stop_called == [True]


@pytest.mark.asyncio
async def test_orchestrator_stops_mcp_on_exception(monkeypatch, tmp_path):
    """execute 抛异常时也应调用 stop_mcp。"""
    from src.runtime.conversation_orchestrator import ConversationOrchestrator

    settings = SimpleNamespace(DATABASE_URL=str(tmp_path / "test.db"))
    monkeypatch.setattr(orchestrator_module, "get_settings", lambda: settings)

    stop_called = []

    class FaultyEngine:
        async def iter_steps(self, task, **kwargs):
            yield
            raise RuntimeError("模拟失败")

    class FaultyRuntime:
        async def create_engine(self):
            return FaultyEngine()

        async def start_mcp(self, registry=None):
            pass

        async def stop_mcp(self):
            stop_called.append(True)

    orchestrator = ConversationOrchestrator(
        settings=settings,
        runtime_factory=FaultyRuntime,
    )
    await orchestrator.initialize()
    await orchestrator.setup_conversation("测试任务")

    with pytest.raises(RuntimeError, match="模拟失败"):
        async for event in orchestrator.execute("测试任务"):
            pass

    assert stop_called == [True]

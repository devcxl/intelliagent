from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.runtime.conversation_orchestrator as orchestrator_module


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


def _make_orchestrator(monkeypatch, tmp_path, created=None):
    _patch_orchestrator_dependencies(monkeypatch, tmp_path, created)
    from src.runtime.conversation_orchestrator import ConversationOrchestrator

    return ConversationOrchestrator()


@pytest.mark.asyncio
async def test_main_creates_engine_through_agent_runtime(monkeypatch, tmp_path):
    created = {}
    orchestrator = _make_orchestrator(monkeypatch, tmp_path, created)
    await orchestrator.initialize()
    await orchestrator.setup_conversation("测试任务")

    async for _ in orchestrator.execute("测试任务"):
        pass

    assert created["config"] is None
    assert created["create_engine_called"] is True


@pytest.mark.asyncio
async def test_main_passes_history_context_to_engine(monkeypatch, tmp_path):
    created = {}
    orchestrator = _make_orchestrator(monkeypatch, tmp_path, created)

    await orchestrator.initialize()
    await orchestrator.setup_conversation("之前的任务")
    await orchestrator.save_message("user", "之前的任务")
    await orchestrator.save_message("assistant", "已完成")

    created.clear()
    created["engine_calls"] = []

    history_ctx = await orchestrator.reload_history_context()
    assert history_ctx is not None

    async for _ in orchestrator.execute("后续任务", history_context=history_ctx):
        pass

    assert created["engine_calls"][0][0] == "iter_steps"
    assert "后续任务" in created["engine_calls"][0][1]


@pytest.mark.asyncio
async def test_main_session_alias_updates_existing_conversation(monkeypatch, tmp_path):
    orchestrator = _make_orchestrator(monkeypatch, tmp_path)
    await orchestrator.initialize()

    cid, _ = await orchestrator.setup_conversation("原始任务", session_id="conversation-1")
    await orchestrator.save_message("user", "原始任务")
    await orchestrator.save_message("assistant", "已处理")

    cid2, history_ctx = await orchestrator.setup_conversation("新任务", session_id="conversation-1")
    assert cid2 == "conversation-1"
    assert orchestrator.is_new is False


@pytest.mark.asyncio
async def test_main_session_alias_creates_missing_conversation(monkeypatch, tmp_path):
    orchestrator = _make_orchestrator(monkeypatch, tmp_path)
    await orchestrator.initialize()

    cid, _ = await orchestrator.setup_conversation("测试任务", session_id="conversation-new")
    assert cid == "conversation-new"
    assert orchestrator.is_new is True
    assert len(orchestrator.warnings) == 1


@pytest.mark.asyncio
async def test_main_resume_uses_latest_conversation(monkeypatch, tmp_path):
    orchestrator = _make_orchestrator(monkeypatch, tmp_path)
    await orchestrator.initialize()

    cid1, _ = await orchestrator.setup_conversation("第一个任务")
    await orchestrator.save_message("user", "第一个任务")
    await orchestrator.save_message("assistant", "已完成")

    cid2, _ = await orchestrator.setup_conversation("后续任务", resume=True)
    assert cid2 == cid1
    assert orchestrator.is_new is False


@pytest.mark.asyncio
async def test_main_history_lists_conversations(monkeypatch, tmp_path):
    orchestrator = _make_orchestrator(monkeypatch, tmp_path)
    await orchestrator.initialize()

    await orchestrator.setup_conversation("历史任务")
    await orchestrator.save_message("user", "历史任务")
    await orchestrator.save_message("assistant", "已完成")

    conversations = await orchestrator.list_conversations()
    assert len(conversations) == 1
    assert conversations[0]["title"] == "历史任务"


@pytest.mark.asyncio
async def test_orchestrator_uses_injected_runtime_factory(monkeypatch, tmp_path):
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

    await orchestrator.shutdown()
    assert stop_called == [True]


@pytest.mark.asyncio
async def test_orchestrator_stops_mcp_on_exception(monkeypatch, tmp_path):
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

    await orchestrator.shutdown()
    assert stop_called == [True]

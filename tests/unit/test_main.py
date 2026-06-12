from __future__ import annotations

from types import SimpleNamespace

import pytest

import src.main as main_module
import src.cli.orchestrator as orchestrator_module


class FakeDatabaseManager:
    def __init__(
        self,
        existing_conversation=None,
        latest_conversation=None,
        conversations=None,
        messages=None,
    ) -> None:
        self.existing_conversation = existing_conversation
        self.latest_conversation = latest_conversation
        self.conversations = conversations or []
        self.messages = messages or []
        self.calls = []

    async def initialize(self) -> None:
        self.calls.append(("initialize",))

    async def create_conversation(self, conversation_id: str, **kwargs):
        self.calls.append(("create_conversation", conversation_id, kwargs))
        return {"id": conversation_id}

    async def get_conversation(self, conversation_id: str):
        self.calls.append(("get_conversation", conversation_id))
        return self.existing_conversation

    async def update_conversation(self, conversation_id: str, **kwargs):
        self.calls.append(("update_conversation", conversation_id, kwargs))
        return True

    async def get_latest_conversation(self):
        self.calls.append(("get_latest_conversation",))
        return self.latest_conversation

    async def list_conversations(self):
        self.calls.append(("list_conversations",))
        return self.conversations

    async def get_messages(self, conversation_id: str):
        self.calls.append(("get_messages", conversation_id))
        return self.messages

    async def save_message(self, *args, **kwargs):
        self.calls.append(("save_message", args, kwargs))
        return "msg-1"

    async def create_run(self, *args, **kwargs):
        self.calls.append(("create_run", args, kwargs))
        return {"id": "run-1"}

    async def save_trace(self, *args, **kwargs):
        self.calls.append(("save_trace", args, kwargs))
        return "trace-1"

    async def update_run(self, *args, **kwargs):
        self.calls.append(("update_run", args, kwargs))
        return True


class FakeEngine:
    def __init__(self, calls=None):
        self.calls = calls

    async def iter_steps(self, task: str, **kwargs):
        if self.calls is not None:
            self.calls.append(("iter_steps", task, kwargs))
        yield {"type": "answer", "iteration": 1, "data": {"answer": "done"}}


class FakeAgentRuntime:
    def __init__(self, runtime_settings):
        self.runtime_settings = runtime_settings

    def create_engine(self):
        return FakeEngine()


def _patch_orchestrator_dependencies(monkeypatch, fake_db, created=None):
    """Patch orchestrator 模块中的依赖，使其使用 fake 实现。"""
    settings = SimpleNamespace(DATABASE_URL=":memory:")

    class RecordingAgentRuntime(FakeAgentRuntime):
        def __init__(self, runtime_settings):
            super().__init__(runtime_settings)
            if created is not None:
                created["settings"] = runtime_settings

        def create_engine(self):
            if created is not None:
                created["create_engine_called"] = True
                return FakeEngine(created.setdefault("engine_calls", []))
            return FakeEngine()

    monkeypatch.setattr(orchestrator_module, "get_settings", lambda: settings)
    monkeypatch.setattr(orchestrator_module, "DatabaseManager", lambda _: fake_db)
    monkeypatch.setattr(orchestrator_module, "AgentRuntime", RecordingAgentRuntime)
    return settings


@pytest.mark.asyncio
async def test_main_creates_engine_through_agent_runtime(monkeypatch):
    created = {}
    fake_db = FakeDatabaseManager()

    def fail_if_direct_llm_is_used(*args, **kwargs):
        raise AssertionError("main.py must create engines through AgentRuntime")

    settings = _patch_orchestrator_dependencies(monkeypatch, fake_db, created)
    monkeypatch.setattr(orchestrator_module, "LLMClient", fail_if_direct_llm_is_used, raising=False)

    await main_module.main(task="测试任务")

    assert created["settings"] is settings
    assert created["create_engine_called"] is True


@pytest.mark.asyncio
async def test_main_passes_history_context_to_engine(monkeypatch):
    created = {}
    fake_db = FakeDatabaseManager(messages=[{"role": "assistant", "content": "之前的答案"}])
    _patch_orchestrator_dependencies(monkeypatch, fake_db, created)

    await main_module.main(task="测试任务")

    assert created["engine_calls"][0][0] == "iter_steps"
    assert created["engine_calls"][0][1] == "测试任务"
    assert "之前的答案" in created["engine_calls"][0][2]["history_context"]


@pytest.mark.asyncio
async def test_main_session_alias_updates_existing_conversation(monkeypatch):
    fake_db = FakeDatabaseManager(existing_conversation={"id": "conversation-1", "title": "旧"})
    _patch_orchestrator_dependencies(monkeypatch, fake_db)

    await main_module.main(task="测试任务", session_id="conversation-1")

    assert ("get_conversation", "conversation-1") in fake_db.calls
    assert any(call[0] == "update_conversation" and call[1] == "conversation-1" for call in fake_db.calls)


@pytest.mark.asyncio
async def test_main_session_alias_creates_missing_conversation(monkeypatch):
    fake_db = FakeDatabaseManager(existing_conversation=None)
    _patch_orchestrator_dependencies(monkeypatch, fake_db)

    await main_module.main(task="测试任务", session_id="conversation-new")

    assert ("get_conversation", "conversation-new") in fake_db.calls
    assert any(call[0] == "create_conversation" and call[1] == "conversation-new" for call in fake_db.calls)


@pytest.mark.asyncio
async def test_main_resume_uses_latest_conversation(monkeypatch):
    fake_db = FakeDatabaseManager(latest_conversation={"id": "conversation-latest", "title": "最近"})
    _patch_orchestrator_dependencies(monkeypatch, fake_db)

    await main_module.main(task="测试任务", resume=True)

    assert ("get_latest_conversation",) in fake_db.calls
    assert any(call[0] == "update_conversation" and call[1] == "conversation-latest" for call in fake_db.calls)


@pytest.mark.asyncio
async def test_main_history_lists_conversations(monkeypatch):
    fake_db = FakeDatabaseManager(conversations=[{
        "id": "conversation-1",
        "title": "历史",
        "status": "finished",
        "updated_at": "now",
    }])
    _patch_orchestrator_dependencies(monkeypatch, fake_db)

    await main_module.main(task="", list_history=True)

    assert ("list_conversations",) in fake_db.calls

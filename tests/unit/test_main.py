from __future__ import annotations

from typing import Any

import pytest

import src.runtime.engine_factory as engine_factory_module
from src.config.unified_config import UnifiedConfig
from src.permission import Decision, PermissionAction
from src.runtime import AgentRuntime


class FakeLLMClient:
    async def chat_async(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        return None


class FakePermissionEngine:
    def check(self, tool_name: str, args: dict[str, Any]) -> Decision:
        return Decision(action=PermissionAction.allow, reason="test")


class FakePermissionCallback:
    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        return True


class FakeEngine:
    def __init__(self, calls: list[tuple[str, Any, Any]]):
        self.calls = calls

    def load_history(self, messages: list[dict[str, Any]]) -> None:
        self.calls.append(("load_history", messages, None))

    async def iter_steps(self, task: str, **kwargs: Any):
        self.calls.append(("iter_steps", task, kwargs))
        yield {"type": "answer", "iteration": 1, "data": {"answer": "done"}}


def _make_runtime(monkeypatch, tmp_path, created: dict[str, Any] | None = None) -> AgentRuntime:
    state = created if created is not None else {}

    class RecordingEngine(FakeEngine):
        def __init__(self, **kwargs: Any):
            super().__init__(state.setdefault("engine_calls", []))
            state.setdefault("engines", []).append(self)

    monkeypatch.setattr(engine_factory_module, "ReactEngine", RecordingEngine)

    config = UnifiedConfig.model_validate(
        {
            "database": {"url": str(tmp_path / "test.db")},
            "skills": {"enabled": False},
        }
    )
    return AgentRuntime(
        config=config,
        llm_client_factory=FakeLLMClient,
        permission_engine_factory=FakePermissionEngine,
        permission_callback_factory=FakePermissionCallback,
    )


@pytest.mark.asyncio
async def test_runtime_execute_creates_engine(monkeypatch, tmp_path):
    created: dict[str, Any] = {}
    runtime = _make_runtime(monkeypatch, tmp_path, created)
    await runtime.initialize()
    await runtime.setup_conversation("测试任务")

    async for _ in runtime.execute("测试任务"):
        pass

    assert len(created["engines"]) == 1
    assert created["engine_calls"][1][0] == "iter_steps"


@pytest.mark.asyncio
async def test_runtime_loads_structured_history_before_execute(monkeypatch, tmp_path):
    created: dict[str, Any] = {}
    runtime = _make_runtime(monkeypatch, tmp_path, created)

    await runtime.initialize()
    await runtime.setup_conversation("之前的任务")
    await runtime.save_message("user", "之前的任务")
    await runtime.save_message("assistant", "已完成")

    async for _ in runtime.execute("后续任务"):
        pass

    assert created["engine_calls"][0] == (
        "load_history",
        [
            {"role": "user", "content": "之前的任务"},
            {"role": "assistant", "content": "已完成"},
        ],
        None,
    )
    assert created["engine_calls"][1] == ("iter_steps", "后续任务", {"reset_state": False})
    assert await runtime.get_message_count(runtime.conversation_id or "") == 4


@pytest.mark.asyncio
async def test_runtime_session_alias_updates_existing_conversation(monkeypatch, tmp_path):
    runtime = _make_runtime(monkeypatch, tmp_path)
    await runtime.initialize()

    cid = await runtime.setup_conversation("原始任务", session_id="conversation-1")
    await runtime.save_message("user", "原始任务")
    await runtime.save_message("assistant", "已处理")

    cid2 = await runtime.setup_conversation("新任务", session_id="conversation-1")
    assert cid == "conversation-1"
    assert cid2 == "conversation-1"
    assert runtime.is_new is False


@pytest.mark.asyncio
async def test_runtime_session_alias_creates_missing_conversation(monkeypatch, tmp_path):
    runtime = _make_runtime(monkeypatch, tmp_path)
    await runtime.initialize()

    cid = await runtime.setup_conversation("测试任务", session_id="conversation-new")
    assert cid == "conversation-new"
    assert runtime.is_new is True
    assert len(runtime.warnings) == 1


@pytest.mark.asyncio
async def test_runtime_resume_uses_latest_conversation(monkeypatch, tmp_path):
    runtime = _make_runtime(monkeypatch, tmp_path)
    await runtime.initialize()

    cid1 = await runtime.setup_conversation("第一个任务")
    await runtime.save_message("user", "第一个任务")
    await runtime.save_message("assistant", "已完成")

    cid2 = await runtime.setup_conversation("后续任务", resume=True)
    assert cid2 == cid1
    assert runtime.is_new is False


@pytest.mark.asyncio
async def test_runtime_history_lists_conversations(monkeypatch, tmp_path):
    runtime = _make_runtime(monkeypatch, tmp_path)
    await runtime.initialize()

    await runtime.setup_conversation("历史任务")
    await runtime.save_message("user", "历史任务")
    await runtime.save_message("assistant", "已完成")

    conversations = await runtime.list_conversations()
    assert len(conversations) == 1
    assert conversations[0]["title"] == "历史任务"


@pytest.mark.asyncio
async def test_runtime_shutdown_stops_mcp(monkeypatch, tmp_path):
    runtime = _make_runtime(monkeypatch, tmp_path)
    stopped = []

    class FakeMCPManager:
        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            stopped.append(True)

    runtime._mcp_manager = FakeMCPManager()
    await runtime.shutdown()

    assert stopped == [True]

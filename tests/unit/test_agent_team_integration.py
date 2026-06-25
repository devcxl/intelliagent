"""Agent Team 运行时集成测试 — 验证 AgentRuntime 注入上下文。"""

import asyncio
from typing import Any

from src.config.unified_config import UnifiedConfig
from src.permission import Decision, PermissionAction
from src.runtime import AgentRuntime
from src.tools.agent_team_tools import _agent_team_ctx, get_contacts, set_agent_team_context


class _FakeLLMClient:
    async def chat_async(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        return None


class _FakePermissionEngine:
    def check(self, tool_name: str, args: dict[str, Any]) -> Decision:
        return Decision(action=PermissionAction.allow, reason="test")


class _FakePermissionCallback:
    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        return True


class _FakeReactEngine:
    def __init__(self, **kwargs):
        pass


def _make_runtime(tmp_path):
    """创建最小化 AgentRuntime 实例（绕过真实依赖）。"""
    config = UnifiedConfig.model_validate(
        {
            "database": {"url": str(tmp_path / "test.db")},
            "skills": {"enabled": False},
        }
    )
    return AgentRuntime(
        config=config,
        llm_client_factory=lambda: _FakeLLMClient(),
        permission_engine_factory=lambda: _FakePermissionEngine(),
        permission_callback_factory=lambda: _FakePermissionCallback(),
    )


def test_runtime_sets_agent_team_context(monkeypatch, tmp_path):
    """AgentRuntime.setup_conversation() 应注入 (session_factory, agent_id)。"""
    import src.runtime.agent_runtime as agent_runtime_module

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", _FakeReactEngine)

    async def _run():
        runtime = _make_runtime(tmp_path)
        await runtime.initialize()
        await runtime.setup_conversation(task="test")
        ctx = _agent_team_ctx.get()
        assert ctx is not None, "上下文应被设置"
        factory, agent_id = ctx
        assert agent_id == "agent-001", f"agent_id 应为默认值 'agent-001'，实际为 {agent_id}"
        set_agent_team_context(None, None)

    asyncio.run(_run())


def test_tool_calls_after_context_injection(monkeypatch, tmp_path):
    """AgentRuntime 设置上下文后，tool 不再返回 CONTEXT_NOT_INITIALIZED。"""
    import src.runtime.agent_runtime as agent_runtime_module

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", _FakeReactEngine)

    async def _run():
        runtime = _make_runtime(tmp_path)
        await runtime.initialize()
        await runtime.setup_conversation(task="test")
        result = await get_contacts()
        assert "CONTEXT_NOT_INITIALIZED" not in result, (
            f"上下文已注入，不应返回 CONTEXT_NOT_INITIALIZED，实际: {result}"
        )
        set_agent_team_context(None, None)

    asyncio.run(_run())

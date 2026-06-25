"""Agent Team 运行时集成测试 — 验证 AgentRuntime 持有独立工具注册表。"""

import asyncio
from typing import Any

from src.config.unified_config import UnifiedConfig
from src.permission import Decision, PermissionAction
from src.runtime import AgentRuntime


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


def _make_runtime(tmp_path):
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


def test_runtime_registers_agent_team_tools(tmp_path):
    async def _run():
        runtime = _make_runtime(tmp_path)
        await runtime.initialize()
        await runtime.setup_conversation(task="test")

        names = runtime._tool_registry.list_tool_names()
        assert "send_message" in names
        assert "get_contacts" in names
        await runtime.shutdown()

    asyncio.run(_run())


def test_tool_calls_after_runtime_setup(tmp_path):
    async def _run():
        runtime = _make_runtime(tmp_path)
        await runtime.initialize()
        await runtime.setup_conversation(task="test")

        result = await runtime._tool_registry.call_tool("get_contacts")
        assert "CONTEXT_NOT_INITIALIZED" not in result
        await runtime.shutdown()

    asyncio.run(_run())

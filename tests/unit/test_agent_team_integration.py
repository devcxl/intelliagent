"""Agent Team 运行时集成测试 — 验证 create_engine() 注入上下文。"""

import asyncio

import src.runtime.agent_runtime as agent_runtime_module
from src.config.unified_config import UnifiedConfig
from src.runtime import AgentRuntime
from src.tools.agent_team_tools import _agent_team_ctx, get_contacts, set_agent_team_context


class _FakeLLMClient:
    pass


class _FakePermissionEngine:
    pass


class _FakePermissionCallback:
    pass


class _FakeReactEngine:
    def __init__(self, **kwargs):
        pass


def _make_runtime(config):
    """创建最小化 AgentRuntime 实例（绕过真实依赖）。"""
    return AgentRuntime(
        config=config,
        llm_client_factory=lambda: _FakeLLMClient(),
        permission_engine_factory=lambda: _FakePermissionEngine(),
        permission_callback_factory=lambda: _FakePermissionCallback(),
    )


def test_create_engine_injects_agent_team_context(monkeypatch, tmp_path):
    """AgentRuntime.create_engine() 应注入 (db_path, agent_id) 到 _agent_team_ctx。"""
    monkeypatch.setattr(agent_runtime_module, "ReactEngine", _FakeReactEngine)
    db_file = tmp_path / "test.db"
    config = UnifiedConfig.model_validate({
        "database": {"url": f"sqlite:///{db_file}"},
        "workspace": {"dir": str(tmp_path)},
    })

    async def _run():
        runtime = _make_runtime(config)
        await runtime.create_engine()
        ctx = _agent_team_ctx.get()
        assert ctx is not None, "上下文应被设置"
        db_path, agent_id = ctx
        assert db_path == str(db_file), f"db_path 应为 {db_file}，实际为 {db_path}"
        assert agent_id == "agent-001", f"agent_id 应为默认值 'agent-001'，实际为 {agent_id}"
        set_agent_team_context(None, None)

    asyncio.run(_run())


def test_create_engine_with_custom_agent_id(monkeypatch, tmp_path):
    """验证从 config 获取自定义 agent_id。"""
    monkeypatch.setattr(agent_runtime_module, "ReactEngine", _FakeReactEngine)
    db_file = tmp_path / "test.db"
    config = UnifiedConfig.model_validate({
        "database": {"url": f"sqlite:///{db_file}"},
        "workspace": {"dir": str(tmp_path)},
    })
    # UnifiedConfig 无 agent_id 字段，通过 object.__setattr__ 注入
    object.__setattr__(config, "agent_id", "custom-agent-42")

    async def _run():
        runtime = _make_runtime(config)
        await runtime.create_engine()
        ctx = _agent_team_ctx.get()
        assert ctx is not None
        _, agent_id = ctx
        assert agent_id == "custom-agent-42"
        set_agent_team_context(None, None)

    asyncio.run(_run())


def test_tool_calls_after_context_injection(monkeypatch, tmp_path):
    """Engine 创建后，tool 不再返回 CONTEXT_NOT_INITIALIZED。"""
    monkeypatch.setattr(agent_runtime_module, "ReactEngine", _FakeReactEngine)
    db_file = tmp_path / "test.db"
    config = UnifiedConfig.model_validate({
        "database": {"url": f"sqlite:///{db_file}"},
        "workspace": {"dir": str(tmp_path)},
    })

    async def _run():
        runtime = _make_runtime(config)
        await runtime.create_engine()
        result = await get_contacts()
        assert "CONTEXT_NOT_INITIALIZED" not in result, (
            f"上下文已注入，不应返回 CONTEXT_NOT_INITIALIZED，实际: {result}"
        )
        set_agent_team_context(None, None)

    asyncio.run(_run())

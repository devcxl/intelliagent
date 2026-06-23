"""AgentRuntime Skill 集成测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.runtime.agent_runtime import AgentRuntime


def test_skill_tool_registered_in_default_registry():
    """skill 工具已注册到 _default_registry。"""
    from src.tools.registry import _default_registry

    names = _default_registry.list_tool_names()
    assert "skill" in names


def test_skill_tool_has_correct_parameters():
    """skill 工具参数定义正确。"""
    from src.tools.registry import _default_registry

    tool_def = _default_registry._tools.get("skill")
    assert tool_def is not None
    assert "name" in tool_def.parameters
    assert tool_def.parameters["name"]["required"] is True


async def test_runtime_create_engine_with_skills(tmp_path):
    """AgentRuntime 创建引擎时加载 skills 并传入 ReactEngine。"""
    # 创建测试 skill
    skill_dir = tmp_path / ".agents" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\n# Test Skill\n\nInstructions."
    )

    config = MagicMock()
    config.workspace.dir = str(tmp_path)
    config.get_model_context_limit.return_value = None
    config.provider = {}
    config.model = None
    config.skills.enabled = True
    config.skills.project_paths = [str(tmp_path / ".agents" / "skills")]
    config.skills.user_paths = []
    config.permissions.rules = []
    config.permissions.external_directories = []
    config.mcp = {}

    runtime = AgentRuntime(
        config=config,
        llm_client_factory=MagicMock,
        permission_engine_factory=MagicMock,
        permission_callback_factory=MagicMock,
    )

    engine = await runtime.create_engine()
    assert engine._skill_registry is not None
    assert engine._skill_registry.get("test-skill") is not None


async def test_runtime_skills_disabled(tmp_path):
    """skills.enabled = False 时跳过 skill 加载。"""
    config = MagicMock()
    config.workspace.dir = str(tmp_path)
    config.get_model_context_limit.return_value = None
    config.provider = {}
    config.model = None
    config.skills.enabled = False
    config.skills.project_paths = []
    config.skills.user_paths = []
    config.permissions.rules = []
    config.permissions.external_directories = []
    config.mcp = {}

    runtime = AgentRuntime(
        config=config,
        llm_client_factory=MagicMock,
        permission_engine_factory=MagicMock,
        permission_callback_factory=MagicMock,
    )

    engine = await runtime.create_engine()
    assert engine._skill_registry is None

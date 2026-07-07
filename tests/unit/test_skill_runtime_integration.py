"""AgentRuntime Skill 集成测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.config.unified_config import UnifiedConfig
from src.runtime import build_runtime_components


def test_skill_tool_registered_in_default_registry():
    """skill 工具已注册到 Runtime 级 ToolRegistry。"""
    from src.skills.registry import SkillRegistry
    from src.skills.tool import SkillTool
    from src.tools.registry import ToolRegistry, register_builtin_tools, register_skill_tool

    registry = ToolRegistry()
    register_builtin_tools(registry)
    register_skill_tool(registry, SkillTool(SkillRegistry()))
    names = registry.list_tool_names()
    assert "skill" in names


def test_skill_tool_has_correct_parameters():
    """skill 工具参数定义正确。"""
    from src.skills.registry import SkillRegistry
    from src.skills.tool import SkillTool
    from src.tools.registry import ToolRegistry, register_builtin_tools, register_skill_tool

    registry = ToolRegistry()
    register_builtin_tools(registry)
    register_skill_tool(registry, SkillTool(SkillRegistry()))

    tool_def = registry._tools.get("skill")
    assert tool_def is not None
    assert "name" in tool_def.parameters
    assert tool_def.parameters["name"]["required"] is True


async def test_runtime_assembly_creates_engine_with_skills(tmp_path):
    """Runtime assembly 创建引擎时加载 skills 并传入 ReactEngine。"""
    # 创建测试 skill
    skill_dir = tmp_path / ".agents" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\n# Test Skill\n\nInstructions."
    )

    config = UnifiedConfig.model_validate(
        {
            "workspace": {"dir": str(tmp_path)},
            "database": {"url": f"sqlite+aiosqlite:///{tmp_path}/test.db"},
            "skills": {"enabled": True, "project_paths": [".agents/skills"], "user_paths": []},
        }
    )

    components = build_runtime_components(
        config=config,
        llm_client_provider=MagicMock,
        permission_engine_factory=MagicMock,
        permission_callback_factory=MagicMock,
    )

    try:
        engine = components.engine_factory.create()
        assert engine._skill_registry is not None
        assert engine._skill_registry.get("test-skill") is not None
    finally:
        await components.database.shutdown()


async def test_runtime_skills_disabled(tmp_path):
    """skills.enabled = False 时跳过 skill 加载。"""
    config = UnifiedConfig.model_validate(
        {
            "workspace": {"dir": str(tmp_path)},
            "database": {"url": f"sqlite+aiosqlite:///{tmp_path}/test.db"},
            "skills": {"enabled": False, "project_paths": [], "user_paths": []},
        }
    )

    components = build_runtime_components(
        config=config,
        llm_client_provider=MagicMock,
        permission_engine_factory=MagicMock,
        permission_callback_factory=MagicMock,
    )

    try:
        engine = components.engine_factory.create()
        assert engine._skill_registry is None
    finally:
        await components.database.shutdown()

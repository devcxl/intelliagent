"""ReactEngine Skill 集成测试。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.core.constants import DEFAULT_SYSTEM_PROMPT
from src.core.react_engine import ReactEngine
from src.skills.model import SkillDef, SkillFrontmatter
from src.skills.registry import SkillRegistry


def _make_skill(name: str, desc: str) -> SkillDef:
    return SkillDef(
        frontmatter=SkillFrontmatter(name=name, description=desc),
        body=f"# {name}\n\nInstructions.",
        source_path=Path("/tmp/skills"),
    )


def test_engine_initializes_with_skill_registry():
    """ReactEngine 接收 skill_registry 参数。"""
    reg = SkillRegistry()
    reg.register(_make_skill("test", "Test skill"))
    engine = ReactEngine(
        llm_client=MagicMock(),
        skill_registry=reg,
    )
    assert engine._skill_registry is reg


def test_system_prompt_includes_available_skills():
    """system prompt 包含 available_skills XML 块。"""
    reg = SkillRegistry()
    reg.register(_make_skill("git-release", "Create releases"))
    engine = ReactEngine(
        llm_client=MagicMock(),
        skill_registry=reg,
    )

    # 模拟 run() 中 system prompt 的构建过程
    msg = engine._build_system_message()
    assert msg["role"] == "system"
    content = msg["content"]
    assert DEFAULT_SYSTEM_PROMPT in content
    assert "<available_skills>" in content
    assert "<name>git-release</name>" in content
    assert "skill 工具加载其完整指令" in content


def test_system_prompt_without_skill_registry():
    """无 skill_registry 时 system prompt 不变。"""
    engine = ReactEngine(llm_client=MagicMock())
    msg = engine._build_system_message()
    content = msg["content"]
    assert content == DEFAULT_SYSTEM_PROMPT
    assert "<available_skills>" not in content


def test_system_prompt_empty_registry():
    """空注册表时 system prompt 不含 XML 块（避免浪费 token）。"""
    reg = SkillRegistry()
    engine = ReactEngine(llm_client=MagicMock(), skill_registry=reg)
    msg = engine._build_system_message()
    content = msg["content"]
    assert content == DEFAULT_SYSTEM_PROMPT
    assert "<available_skills>" not in content

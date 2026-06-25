"""SkillRegistry 和 skill 工具测试。"""

from __future__ import annotations

from pathlib import Path

from src.skills.model import SkillDef, SkillFrontmatter
from src.skills.registry import SkillRegistry
from src.skills.tool import SkillTool


def _make_skill(name: str, desc: str, body: str = "Body.") -> SkillDef:
    return SkillDef(
        frontmatter=SkillFrontmatter(name=name, description=desc),
        body=body,
        source_path=Path("/tmp/skills"),
    )


# ============================================================================
# SkillRegistry
# ============================================================================


def test_register_and_get():
    """注册 skill 后能按名称获取。"""
    reg = SkillRegistry()
    s = _make_skill("my-skill", "My skill")
    reg.register(s)
    assert reg.get("my-skill") is s


def test_register_duplicate_name_ignored():
    """同名 skill 后注册的被忽略。"""
    reg = SkillRegistry()
    s1 = _make_skill("dup", "First")
    s2 = _make_skill("dup", "Second")
    reg.register(s1)
    reg.register(s2)
    assert reg.get("dup").frontmatter.description == "First"


def test_get_nonexistent_returns_none():
    """不存在的 skill 返回 None。"""
    reg = SkillRegistry()
    assert reg.get("nonexistent") is None


def test_generate_available_skills_xml():
    """生成正确的 available_skills XML 块。"""
    reg = SkillRegistry()
    reg.register(_make_skill("git-release", "Create releases"))
    reg.register(_make_skill("code-review", "Review code"))

    xml = reg.generate_available_skills_xml()
    assert "<available_skills>" in xml
    assert "</available_skills>" in xml
    assert "<name>git-release</name>" in xml
    assert "<description>Create releases</description>" in xml
    assert "<name>code-review</name>" in xml
    assert "<description>Review code</description>" in xml


def test_generate_xml_with_special_chars():
    """XML 特殊字符被正确转义。"""
    reg = SkillRegistry()
    reg.register(_make_skill("test", 'Use foo & bar < baz > "qux"'))
    xml = reg.generate_available_skills_xml()
    assert "&amp;" in xml
    assert "&lt;" in xml
    assert "&gt;" in xml
    assert "&quot;" in xml


def test_generate_xml_empty_registry():
    """空注册表返回空 XML 块。"""
    reg = SkillRegistry()
    xml = reg.generate_available_skills_xml()
    assert xml == "<available_skills>\n</available_skills>"


def test_list_names():
    """list_names 返回所有 skill 名称。"""
    reg = SkillRegistry()
    reg.register(_make_skill("a", "A"))
    reg.register(_make_skill("b", "B"))
    assert sorted(reg.list_names()) == ["a", "b"]


def test_load_all():
    """load_all 批量注册。"""
    reg = SkillRegistry()
    skills = [_make_skill("a", "A"), _make_skill("b", "B")]
    reg.load_all(skills)
    assert reg.list_names() == ["a", "b"]


# ============================================================================
# SkillTool
# ============================================================================


async def test_skill_tool_returns_body():
    """skill 工具返回 skill 的完整 body。"""
    reg = SkillRegistry()
    s = _make_skill("my-skill", "My skill", "# Full instructions\n\nDo X.")
    reg.register(s)

    result = await SkillTool(reg).load(name="my-skill")
    assert '"status": "ok"' in result
    assert "Full instructions" in result


async def test_skill_tool_unknown_skill():
    """不存在的 skill 返回错误。"""
    reg = SkillRegistry()

    result = await SkillTool(reg).load(name="nonexistent")
    assert '"status": "error"' in result
    assert "UNKNOWN_SKILL" in result

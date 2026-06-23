"""Skill 数据模型测试。"""

from src.skills.model import SkillDef, SkillFrontmatter


def test_skill_frontmatter_required_fields():
    """name 和 description 为必填。"""
    fm = SkillFrontmatter(name="my-skill", description="我的技能")
    assert fm.name == "my-skill"
    assert fm.description == "我的技能"
    assert fm.license is None
    assert fm.compatibility is None
    assert fm.metadata == {}


def test_skill_frontmatter_optional_fields():
    """license、compatibility、metadata 为可选。"""
    fm = SkillFrontmatter(
        name="test-skill",
        description="测试技能",
        license="MIT",
        compatibility="opencode",
        metadata={"tags": ["python"]},
    )
    assert fm.license == "MIT"
    assert fm.compatibility == "opencode"
    assert fm.metadata == {"tags": ["python"]}


def test_skill_def_creation():
    """SkillDef 包含 frontmatter、body 和 source_path。"""
    from pathlib import Path

    fm = SkillFrontmatter(name="my-skill", description="我的技能")
    sd = SkillDef(
        frontmatter=fm,
        body="# 指令正文\n\n## 使用场景\n",
        source_path=Path("/tmp/skills/my-skill"),
    )
    assert sd.frontmatter.name == "my-skill"
    assert "指令正文" in sd.body
    assert sd.source_path == Path("/tmp/skills/my-skill")

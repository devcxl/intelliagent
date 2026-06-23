"""SkillLoader 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.skills.loader import SkillLoader


@pytest.fixture
def skill_dirs(tmp_path: Path) -> dict[str, Path]:
    """创建测试用的 skill 目录结构。"""
    project = tmp_path / "project" / ".agents" / "skills"
    user = tmp_path / "user" / ".config" / "opencode" / "skills"

    for base in [project, user]:
        base.mkdir(parents=True)

    # 项目级 skill：git-release
    (project / "git-release").mkdir()
    (project / "git-release" / "SKILL.md").write_text(
        "---\n"
        "name: git-release\n"
        "description: Create consistent releases and changelogs\n"
        "license: MIT\n"
        "---\n"
        "# Git Release\n\n"
        "Draft release notes from merged PRs."
    )

    # 用户级 skill：code-review
    (user / "code-review").mkdir()
    (user / "code-review" / "SKILL.md").write_text(
        "---\n"
        "name: code-review\n"
        "description: Review code for quality and security\n"
        "---\n"
        "# Code Review\n\n"
        "Check for security issues and code quality."
    )

    # 同名 skill（项目级应优先）
    (project / "duplicate").mkdir()
    (project / "duplicate" / "SKILL.md").write_text(
        "---\n"
        "name: duplicate\n"
        "description: project level\n"
        "---\n"
        "Project version."
    )
    (user / "duplicate").mkdir()
    (user / "duplicate" / "SKILL.md").write_text(
        "---\n"
        "name: duplicate\n"
        "description: user level\n"
        "---\n"
        "User version."
    )

    return {"project": project, "user": user}


def test_discover_skills_from_directories(skill_dirs):
    """SkillLoader 能从项目级和用户级目录发现 SKILL.md。"""
    skills = SkillLoader.load(
        project_paths=[skill_dirs["project"]],
        user_paths=[skill_dirs["user"]],
    )
    names = {s.frontmatter.name for s in skills}
    assert "git-release" in names
    assert "code-review" in names


def test_skill_body_parsed_correctly(skill_dirs):
    """SKILL.md 的 body 部分正确解析。"""
    skills = SkillLoader.load(
        project_paths=[skill_dirs["project"]],
        user_paths=[skill_dirs["user"]],
    )
    git_skill = next(s for s in skills if s.frontmatter.name == "git-release")
    assert "Git Release" in git_skill.body
    assert "Draft release notes" in git_skill.body


def test_project_skill_overrides_user_skill(skill_dirs):
    """同名 skill 时项目级优先于用户级。"""
    skills = SkillLoader.load(
        project_paths=[skill_dirs["project"]],
        user_paths=[skill_dirs["user"]],
    )
    dup = next(s for s in skills if s.frontmatter.name == "duplicate")
    assert dup.frontmatter.description == "project level"
    assert "Project version" in dup.body


def test_empty_directories_return_empty_list():
    """空目录时返回空列表，不是错误。"""
    skills = SkillLoader.load(
        project_paths=[Path("/tmp/nonexistent_skills_xyz")],
        user_paths=[Path("/tmp/nonexistent_user_skills_xyz")],
    )
    assert skills == []


def test_missing_yaml_frontmatter_skipped(tmp_path):
    """缺少 YAML frontmatter 的 SKILL.md 被跳过。"""
    d = tmp_path / "skills" / "bad"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("# No frontmatter\n\nJust body.")
    skills = SkillLoader.load(
        project_paths=[tmp_path / "skills"],
        user_paths=[],
    )
    assert len(skills) == 0


def test_missing_name_or_description_skipped(tmp_path):
    """缺少 name 或 description 的 skill 被跳过。"""
    d = tmp_path / "skills" / "no-name"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\n"
        "description: no name here\n"
        "---\n"
        "Body."
    )
    skills = SkillLoader.load(
        project_paths=[tmp_path / "skills"],
        user_paths=[],
    )
    assert len(skills) == 0


def test_source_path_set_correctly(skill_dirs):
    """SkillDef.source_path 指向 SKILL.md 所在目录。"""
    skills = SkillLoader.load(
        project_paths=[skill_dirs["project"]],
        user_paths=[skill_dirs["user"]],
    )
    git = next(s for s in skills if s.frontmatter.name == "git-release")
    assert git.source_path == skill_dirs["project"] / "git-release"


def test_recursive_discovery(tmp_path):
    """递归扫描嵌套目录结构中的 SKILL.md。"""
    nested = tmp_path / ".agents" / "skills" / "category" / "nested-skill"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text(
        "---\n"
        "name: nested-skill\n"
        "description: Nested in category\n"
        "---\n"
        "# Nested skill"
    )
    skills = SkillLoader.load(
        project_paths=[tmp_path / ".agents" / "skills"],
        user_paths=[],
    )
    names = {s.frontmatter.name for s in skills}
    assert "nested-skill" in names


def test_invalid_yaml_syntax_skipped(tmp_path):
    """YAML 语法错误的 SKILL.md 被跳过。"""
    d = tmp_path / "skills" / "bad-yaml"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\n"
        "name: [broken: syntax\n"
        "---\n"
        "Body."
    )
    skills = SkillLoader.load(
        project_paths=[tmp_path / "skills"],
        user_paths=[],
    )
    assert len(skills) == 0


def test_frontmatter_is_not_object_skipped(tmp_path):
    """frontmatter 内容不是对象时跳过。"""
    d = tmp_path / "skills" / "bad-fm"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\n"
        "- item1\n"
        "- item2\n"
        "---\n"
        "Body."
    )
    skills = SkillLoader.load(
        project_paths=[tmp_path / "skills"],
        user_paths=[],
    )
    assert len(skills) == 0

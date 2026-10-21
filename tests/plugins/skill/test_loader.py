"""SKILL.md 发现与解析测试：frontmatter 元数据、正文、source_path/location 语义与扫描优先级（issue #62）。"""

from __future__ import annotations

from pathlib import Path

from src.plugins.skill import load_skills


def write_skill(base: Path, name: str, description: str, body: str = "指令正文") -> Path:
    """在一个 skill 目录下写 SKILL.md，返回文件路径。"""
    skill_file = base / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n", encoding="utf-8")
    return skill_file


class TestParseSkillFile:
    def test_parses_frontmatter_metadata_and_markdown_body(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "demo", "演示用 skill", body="# 标题\n\n详细指令")

        skills = load_skills(project_paths=[tmp_path])

        assert len(skills) == 1
        skill = skills[0]
        assert skill.name == "demo"
        assert skill.description == "演示用 skill"
        assert skill.body == "# 标题\n\n详细指令"

    def test_location_is_readable_skill_file_and_source_path_is_its_directory(self, tmp_path: Path) -> None:
        skill_file = write_skill(tmp_path, "demo", "演示")

        skills = load_skills(project_paths=[tmp_path])
        skill = skills[0]

        # location 指向 SKILL.md 本身（本票保证可读）；source_path 是所在目录（ADR 0004 Layer 3 引用文件）。
        assert skill.location == skill_file.resolve()
        assert skill.location.is_file()
        assert skill.source_path == skill_file.resolve().parent

    def test_unquoted_description_containing_colon_still_parses(self, tmp_path: Path) -> None:
        skill_file = tmp_path / "colon" / "SKILL.md"
        skill_file.parent.mkdir(parents=True)
        skill_file.write_text(
            "---\nname: colon\ndescription: Use when: (1) reviewing code\n---\n\n正文\n", encoding="utf-8"
        )

        skills = load_skills(project_paths=[tmp_path])

        assert len(skills) == 1
        assert skills[0].description == "Use when: (1) reviewing code"

    def test_invalid_skill_files_are_skipped(self, tmp_path: Path) -> None:
        no_frontmatter = tmp_path / "a" / "SKILL.md"
        no_frontmatter.parent.mkdir(parents=True)
        no_frontmatter.write_text("只有正文\n", encoding="utf-8")
        missing_name = tmp_path / "b" / "SKILL.md"
        missing_name.parent.mkdir(parents=True)
        missing_name.write_text("---\ndescription: 缺 name\n---\n\n正文\n", encoding="utf-8")
        missing_description = tmp_path / "c" / "SKILL.md"
        missing_description.parent.mkdir(parents=True)
        missing_description.write_text("---\nname: c\n---\n\n正文\n", encoding="utf-8")

        assert load_skills(project_paths=[tmp_path]) == ()


class TestScanPriority:
    def test_project_level_skill_wins_over_user_level_on_name_collision(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "project"
        user_dir = tmp_path / "user"
        write_skill(project_dir, "demo", "项目级")
        write_skill(user_dir, "demo", "用户级")

        skills = load_skills(project_paths=[project_dir], user_paths=[user_dir])

        assert len(skills) == 1
        assert skills[0].description == "项目级"

    def test_missing_scan_directories_are_ignored(self, tmp_path: Path) -> None:
        assert load_skills(project_paths=[tmp_path / "不存在"], user_paths=[tmp_path / "也没有"]) == ()

    def test_nested_skill_directories_are_discovered(self, tmp_path: Path) -> None:
        write_skill(tmp_path / "a/b", "nested", "嵌套目录里的 skill")

        skills = load_skills(user_paths=[tmp_path])

        assert [skill.name for skill in skills] == ["nested"]

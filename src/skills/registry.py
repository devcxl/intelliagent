"""SkillRegistry — 注册表，管理 SkillDef 集合。"""

from __future__ import annotations

from src.skills.model import SkillDef


class SkillRegistry:
    """Skill 注册表。

    持有 SkillDef 集合，提供按名称查找和生成 available_skills XML 的能力。
    """

    def __init__(self) -> None:
        self._skills: dict[str, SkillDef] = {}

    def register(self, skill: SkillDef) -> None:
        """注册单个 skill。同名时保留已注册的（先到先得）。"""
        if skill.frontmatter.name not in self._skills:
            self._skills[skill.frontmatter.name] = skill

    def get(self, name: str) -> SkillDef | None:
        """按名称查找 skill。"""
        return self._skills.get(name)

    def generate_available_skills_xml(self) -> str:
        """生成 available_skills XML 块。"""
        parts = ["<available_skills>"]
        for s in self._skills.values():
            parts.append("  <skill>")
            parts.append(f"    <name>{_escape_xml(s.frontmatter.name)}</name>")
            parts.append(f"    <description>{_escape_xml(s.frontmatter.description)}</description>")
            parts.append("  </skill>")
        parts.append("</available_skills>")
        return "\n".join(parts)

    def list_names(self) -> list[str]:
        """列出所有已注册 skill 名称。"""
        return list(self._skills.keys())

    def load_all(self, skills: list[SkillDef]) -> None:
        """批量注册 skill 列表。"""
        for s in skills:
            self.register(s)


def _escape_xml(text: str) -> str:
    """对 XML 特殊字符进行转义。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

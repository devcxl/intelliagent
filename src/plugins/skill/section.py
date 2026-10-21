"""`<available_skills>` prompt section 渲染：纯函数、字节级稳定（pi-engine-principles §3.5、issue #62）。"""

from __future__ import annotations

from collections.abc import Iterable

from src.plugins.skill.model import Skill


def render_available_skills(skills: Iterable[Skill]) -> str:
    """skill 元数据 → `<available_skills>` section，只含 name/description/location（正文不注入）。

    纯函数：同输入同输出，压缩的 prompt checkpoint 重建 section 快照一致；
    按 name 排序，输出与发现顺序无关。
    """
    lines = ["<available_skills>"]
    for skill in sorted(skills, key=lambda item: item.name):
        lines.append("  <skill>")
        lines.append(f"    <name>{_escape_xml(skill.name)}</name>")
        lines.append(f"    <description>{_escape_xml(skill.description)}</description>")
        lines.append(f"    <location>{_escape_xml(str(skill.location))}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


def _escape_xml(text: str) -> str:
    """XML 特殊字符转义，防止元数据破坏 section 结构。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

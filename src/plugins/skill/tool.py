"""skill_load 工具：按需加载 skill 正文，返回 source_path 以支持引用附带文件（issue #62）。"""

from __future__ import annotations

from src.plugins.basic_tools.result import tool_error, tool_success
from src.plugins.basic_tools.tool import ToolSpec
from src.plugins.skill.catalog import SkillCatalog

MAX_BODY_CHARS = 50_000


def skill_load_tool(catalog: SkillCatalog) -> ToolSpec:
    """构造 skill_load 工具能力提供者（CONTEXT 术语：Tool）。"""

    async def load_skill(name: str) -> str:
        skill = catalog.get(name)
        if skill is None:
            return tool_error("UNKNOWN_SKILL", f"未知 skill: {name}", name=name)
        body, truncated = _clamp_body(skill.body)
        return tool_success(
            name=skill.name,
            description=skill.description,
            source_path=str(skill.source_path),
            body=body,
            body_length=len(skill.body),
            truncated=truncated,
        )

    return ToolSpec(
        name="skill_load",
        description="按名称加载 skill 的完整指令正文；返回 source_path 供引用 skill 目录内的附带文件。",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=load_skill,
    )


def _clamp_body(body: str) -> tuple[str, bool]:
    """大体积保护：正文超限时截断到 MAX_BODY_CHARS，返回 (正文, 是否截断)。"""
    if len(body) <= MAX_BODY_CHARS:
        return body, False
    return body[:MAX_BODY_CHARS], True

"""skill 内置工具 — 按名称加载 skill 的完整指令。"""

from __future__ import annotations

from src.skills.registry import SkillRegistry
from src.tools.response import error_response, success_response


class SkillTool:
    """Skill 工具适配器，显式持有 SkillRegistry。"""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    async def load(self, name: str) -> str:
        """加载指定 skill 的完整指令。"""
        skill = self._registry.get(name)
        if skill is None:
            return error_response(f"未知 skill: {name}", "UNKNOWN_SKILL")

        return success_response({"name": name, "body": skill.body})


__all__ = ["SkillTool"]

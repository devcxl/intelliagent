"""skill 内置工具 — 按名称加载 skill 的完整指令。"""

from __future__ import annotations

from src.skills.registry import SkillRegistry
from src.tools.response import error_response, success_response

# 全局引用，由 AgentRuntime 在初始化时设置
_registry: SkillRegistry | None = None


def set_registry(registry: SkillRegistry) -> None:
    """设置全局 SkillRegistry 引用。"""
    global _registry
    _registry = registry


async def skill_tool(name: str) -> str:
    """加载指定 skill 的完整指令。

    模型调用此工具加载匹配任务的 skill 后，应遵循其中的指示行事。

    Args:
        name: skill 名称

    Returns:
        skill 完整指令文本的 JSON 响应
    """
    if _registry is None:
        return error_response("Skill 系统未初始化", "SKILL_NOT_INITIALIZED")

    skill = _registry.get(name)
    if skill is None:
        return error_response(f"未知 skill: {name}", "UNKNOWN_SKILL")

    return success_response({"name": name, "body": skill.body})

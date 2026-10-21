"""skill 内置插件：一个能力包，注册 skill_load Tool 与 available_skills Hook（ADR 0007 hooks+tools 组合先例）。"""

from __future__ import annotations

from pydantic import BaseModel

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest
from src.core.turn_hooks import PrepareRequestHook
from src.plugins.skill.catalog import SkillCatalog
from src.plugins.skill.prompt import SkillPromptInjector
from src.plugins.skill.tool import skill_load_tool


class SkillPlugin:
    """CONTEXT 术语：Built-in Plugin——元数据进 prompt 稳定 section，正文经 skill_load 按需加载（issue #62）。"""

    def __init__(self, catalog: SkillCatalog) -> None:
        self._catalog = catalog
        self.manifest = Manifest(
            name="skill",
            version="0.1.0",
            api_version=1,
            capabilities=(
                CapabilityDeclaration(kind=CapabilityKind.TOOL, name="skill_load"),
                CapabilityDeclaration(kind=CapabilityKind.HOOK, name="available_skills"),
            ),
        )

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        """注册 skill_load 工具与 available_skills prompt 注入 hook。"""
        registrar.register(CapabilityKind.TOOL, "skill_load", skill_load_tool(self._catalog))
        registrar.register(
            CapabilityKind.HOOK, "available_skills", PrepareRequestHook(callback=SkillPromptInjector(self._catalog))
        )

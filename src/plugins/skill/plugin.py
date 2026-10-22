"""skill 内置插件：一个能力包，注册 skill_load Tool 与 available_skills Hook（ADR 0007 hooks+tools 组合先例）。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest
from src.core.turn_hooks import PrepareRequestHook
from src.plugins.skill.catalog import SkillCatalog
from src.plugins.skill.prompt import SkillPromptInjector
from src.plugins.skill.tool import skill_load_tool


class SkillConfig(BaseModel):
    """skill 插件配置：项目级/用户级扫描路径（项目级同名优先）。"""

    model_config = ConfigDict(extra="forbid")

    project_paths: list[str] = Field(default_factory=lambda: [".agents/skills"])
    user_paths: list[str] = Field(default_factory=lambda: ["~/.config/opencode/skills"])


class SkillPlugin:
    """CONTEXT 术语：Built-in Plugin——元数据进 prompt 稳定 section，正文经 skill_load 按需加载（issue #62）。"""

    def __init__(self, catalog: SkillCatalog | None = None, *, workspace: Path | None = None) -> None:
        self._catalog = catalog
        self._workspace = workspace if workspace is not None else Path.cwd()
        self.manifest = Manifest(
            name="skill",
            version="0.1.0",
            api_version=1,
            capabilities=(
                CapabilityDeclaration(kind=CapabilityKind.TOOL, name="skill_load"),
                CapabilityDeclaration(kind=CapabilityKind.HOOK, name="available_skills"),
            ),
            config_schema=SkillConfig,
        )

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        """注册 skill_load 工具与 available_skills prompt 注入 hook。

        未注入 catalog 时按配置扫描：project_paths 相对 workspace 解析，user_paths 支持 ~ 展开。
        扫描为空也注册工具与 hook（skill_load 返回未找到；hook 不注入空 section）。
        """
        if config is not None and not isinstance(config, SkillConfig):
            raise TypeError(f"skill plugin expects SkillConfig, got {type(config).__name__}")
        catalog = self._catalog if self._catalog is not None else self._load_catalog(config or SkillConfig())
        registrar.register(CapabilityKind.TOOL, "skill_load", skill_load_tool(catalog))
        registrar.register(
            CapabilityKind.HOOK, "available_skills", PrepareRequestHook(callback=SkillPromptInjector(catalog))
        )

    def _load_catalog(self, config: SkillConfig) -> SkillCatalog:
        project_paths = [
            path if path.is_absolute() else self._workspace / path
            for path in (Path(raw).expanduser() for raw in config.project_paths)
        ]
        user_paths = [Path(raw).expanduser() for raw in config.user_paths]
        return SkillCatalog.from_paths(project_paths, user_paths)

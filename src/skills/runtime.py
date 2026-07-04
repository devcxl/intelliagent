from __future__ import annotations

from pathlib import Path

from src.config.unified_config import SkillsConfig
from src.skills.loader import SkillLoader
from src.skills.registry import SkillRegistry


class SkillRuntime:
    def __init__(self, config: SkillsConfig, workspace: Path) -> None:
        self._config = config
        self._workspace = workspace

    def load_registry(self) -> SkillRegistry | None:
        if not self._config.enabled:
            return None

        project_paths = [(self._workspace / p).expanduser().resolve() for p in self._config.project_paths]
        user_paths = [Path(p).expanduser().resolve() for p in self._config.user_paths]

        skills = SkillLoader.load(project_paths=project_paths, user_paths=user_paths)

        if not skills:
            return None

        registry = SkillRegistry()
        registry.load_all(skills)
        return registry


__all__ = ["SkillRuntime"]

"""SkillCatalog：skill 集合的名称索引，供 prompt 注入与 skill_load 共用（issue #62）。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from src.plugins.skill.loader import load_skills
from src.plugins.skill.model import Skill


class SkillCatalog:
    """不可变 skill 集合：按名称查找 + 按名排序的元数据视图（section 稳定性的来源）。"""

    def __init__(self, skills: Iterable[Skill]) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills:
            self._skills.setdefault(skill.name, skill)

    @classmethod
    def from_paths(cls, project_paths: Sequence[Path] = (), user_paths: Sequence[Path] = ()) -> SkillCatalog:
        """从扫描路径构建（项目级优先，见 loader.load_skills）。"""
        return cls(load_skills(project_paths, user_paths))

    def get(self, name: str) -> Skill | None:
        """按名称查找 skill；不存在返回 None。"""
        return self._skills.get(name)

    def skills(self) -> tuple[Skill, ...]:
        """全部 skill，按名称排序——section 渲染顺序与发现顺序无关。"""
        return tuple(self._skills[name] for name in sorted(self._skills))

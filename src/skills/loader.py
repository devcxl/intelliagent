"""SkillLoader — 从文件系统发现和解析 SKILL.md。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

import yaml

from src.skills.model import SkillDef, SkillFrontmatter

logger = logging.getLogger(__name__)


def _parse_skill_file(filepath: Path) -> SkillDef | None:
    """解析单个 SKILL.md 文件，返回 SkillDef。

    解析失败（无 frontmatter、缺少必填字段等）时返回 None。
    """
    content = filepath.read_text(encoding="utf-8")

    # 查找 YAML frontmatter 分隔符
    if not content.startswith("---"):
        logger.warning("SKILL.md 缺少 YAML frontmatter: %s", filepath)
        return None

    rest = content[3:].lstrip()
    end_idx = rest.find("\n---")
    if end_idx == -1:
        logger.warning("SKILL.md YAML frontmatter 未正确关闭: %s", filepath)
        return None

    yaml_block = rest[:end_idx]
    body_start = end_idx + 4  # skip "\n---"
    body = rest[body_start:].strip()

    try:
        raw = yaml.safe_load(yaml_block)
    except yaml.YAMLError as e:
        logger.warning("SKILL.md YAML 解析失败: %s, error=%s", filepath, e)
        return None

    if not isinstance(raw, dict):
        logger.warning("SKILL.md frontmatter 不是对象: %s", filepath)
        return None

    name = raw.get("name")
    description = raw.get("description")

    if not name or not description:
        logger.warning("SKILL.md 缺少 name 或 description: %s", filepath)
        return None

    if not isinstance(name, str):
        logger.warning("SKILL.md name 必须是字符串，实际类型: %s, file=%s", type(name).__name__, filepath)
        return None

    if not isinstance(description, str):
        logger.warning("SKILL.md description 必须是字符串，实际类型: %s, file=%s", type(description).__name__, filepath)
        return None

    fm = SkillFrontmatter(
        name=name,
        description=description,
        license=raw.get("license"),
        compatibility=raw.get("compatibility"),
        metadata=raw.get("metadata", {}),
    )

    return SkillDef(
        frontmatter=fm,
        body=body,
        source_path=filepath.parent.resolve(),
    )


def _scan_paths(paths: Sequence[Path]) -> list[SkillDef]:
    """扫描路径列表，收集所有有效的 SKILL.md。"""
    result: list[SkillDef] = []
    seen: set[str] = set()

    for base in paths:
        if not base.exists() or not base.is_dir():
            logger.debug("Skill 扫描目录不存在，跳过: %s", base)
            continue

        for skill_file in sorted(base.rglob("SKILL.md")):
            sd = _parse_skill_file(skill_file)
            if sd is None:
                continue

            # 同名去重：先扫描的保留（项目级在前 → 优先）
            if sd.frontmatter.name in seen:
                logger.debug("同名 skill 已注册，跳过: %s", sd.frontmatter.name)
                continue
            seen.add(sd.frontmatter.name)
            result.append(sd)

    return result


class SkillLoader:
    """Skill 发现与解析器。

    从配置的路径列表中递归扫描 SKILL.md 文件，
    解析 YAML frontmatter 并返回 SkillDef 列表。
    """

    @staticmethod
    def load(
        project_paths: list[Path] | None = None,
        user_paths: list[Path] | None = None,
    ) -> list[SkillDef]:
        """发现并解析所有 SKILL.md 文件。

        Args:
            project_paths: 项目级扫描路径列表（优先级高）
            user_paths: 用户级扫描路径列表（优先级低）

        Returns:
            按优先级排序的 SkillDef 列表（项目级在前）
        """
        project = project_paths or []
        user = user_paths or []

        # 项目级先扫描，用户级后扫描（同名时项目级保留）
        return _scan_paths(project) + _scan_paths(user)

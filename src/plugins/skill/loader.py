"""SKILL.md 发现与解析：扫描目录、解析 YAML frontmatter 元数据与 Markdown 正文（issue #62）。"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from src.plugins.skill.model import Skill

logger = logging.getLogger(__name__)


def load_skills(project_paths: Sequence[Path] = (), user_paths: Sequence[Path] = ()) -> tuple[Skill, ...]:
    """扫描路径列表收集 SKILL.md：项目级先扫（同名优先），用户级后扫；解析失败的文件跳过。"""
    skills: list[Skill] = []
    seen: set[str] = set()
    for base in (*project_paths, *user_paths):
        if not base.is_dir():
            logger.debug("Skill 扫描目录不存在，跳过: %s", base)
            continue
        for skill_file in sorted(base.rglob("SKILL.md")):
            skill = _parse_skill_file(skill_file)
            if skill is None or skill.name in seen:
                logger.debug("同名 skill 已收录或解析失败，跳过: %s", skill_file)
                continue
            seen.add(skill.name)
            skills.append(skill)
    return tuple(skills)


def _parse_skill_file(skill_file: Path) -> Skill | None:
    """解析单个 SKILL.md；缺 frontmatter、缺必填字段或 YAML 不可解析时返回 None。"""
    content = skill_file.read_text(encoding="utf-8")
    if not content.startswith("---"):
        logger.warning("SKILL.md 缺少 YAML frontmatter: %s", skill_file)
        return None
    rest = content[3:].lstrip()
    end_index = rest.find("\n---")
    if end_index == -1:
        logger.warning("SKILL.md YAML frontmatter 未正确关闭: %s", skill_file)
        return None

    try:
        raw = _load_yaml(rest[:end_index])
    except yaml.YAMLError as exc:
        logger.warning("SKILL.md YAML 解析失败: %s, error=%s", skill_file, exc)
        return None
    if not isinstance(raw, dict):
        logger.warning("SKILL.md frontmatter 不是对象: %s", skill_file)
        return None

    name = raw.get("name")
    description = raw.get("description")
    if not isinstance(name, str) or not name or not isinstance(description, str) or not description:
        logger.warning("SKILL.md 缺少字符串型 name 或 description: %s", skill_file)
        return None

    resolved = skill_file.resolve()
    return Skill(
        name=name,
        description=description,
        location=resolved,
        source_path=resolved.parent,
        body=rest[end_index + 4 :].strip(),
    )


def _load_yaml(block: str) -> Any:
    """解析 frontmatter YAML；纯文本标量含 ": " 时先加引号重试（如 description: Use when: (1) ...）。"""
    try:
        return yaml.safe_load(block)
    except yaml.YAMLError:
        return yaml.safe_load(_quote_colon_values(block))


def _quote_colon_values(text: str) -> str:
    """给含 ": " 的纯文本标量值加双引号，避免被 YAML 解读为 mapping 分隔符。"""
    lines = []
    for line in text.split("\n"):
        matched = re.match(r"^(\w[\w-]*):\s+(.+)$", line)
        if matched and ": " in matched.group(2) and not matched.group(2).startswith(('"', "'")):
            value = matched.group(2).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{matched.group(1)}: "{value}"')
        else:
            lines.append(line)
    return "\n".join(lines)

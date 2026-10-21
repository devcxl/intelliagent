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

# SKILL.md 尺寸上限：YAML alias 可构造膨胀结构（safe_load 防执行不防内存），超限拒绝。
MAX_SKILL_FILE_BYTES = 1_000_000
# frontmatter 分隔符必须独占一行（防 "---oops"、"----" 误判）。
_FENCE = re.compile(r"^---[ \t]*$", re.MULTILINE)


def load_skills(project_paths: Sequence[Path] = (), user_paths: Sequence[Path] = ()) -> tuple[Skill, ...]:
    """扫描路径列表收集 SKILL.md：项目级先扫（同名优先），用户级后扫；解析失败的文件跳过。"""
    skills: list[Skill] = []
    seen: set[str] = set()
    for base in (*project_paths, *user_paths):
        if not base.is_dir():
            logger.debug("Skill 扫描目录不存在，跳过: %s", base)
            continue
        resolved_base = base.resolve()
        for skill_file in sorted(base.rglob("SKILL.md")):
            skill = _parse_skill_file(skill_file, resolved_base)
            if skill is None:
                logger.debug("SKILL.md 解析失败，跳过: %s", skill_file)
                continue
            if skill.name in seen:
                logger.debug("同名 skill 已收录，跳过: %s", skill_file)
                continue
            seen.add(skill.name)
            skills.append(skill)
    return tuple(skills)


def _parse_skill_file(skill_file: Path, scan_root: Path) -> Skill | None:
    """解析单个 SKILL.md；尺寸超限、读取失败、缺 frontmatter、缺必填字段或 YAML 不可解析时返回 None。

    resolve 后校验包含于扫描根：目录内符号链接不得把 location/source_path 引到根外
    （该路径会经 skill_load 返回给模型）。
    """
    try:
        if skill_file.stat().st_size > MAX_SKILL_FILE_BYTES:
            logger.warning("SKILL.md 超过尺寸上限 %d 字节，跳过: %s", MAX_SKILL_FILE_BYTES, skill_file)
            return None
        content = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("SKILL.md 读取失败，跳过: %s, error=%s", skill_file, exc)
        return None
    if not _FENCE.match(content):
        logger.warning("SKILL.md 缺少 YAML frontmatter: %s", skill_file)
        return None
    rest = content[3:].lstrip()
    closing = _FENCE.search(rest)
    if closing is None:
        logger.warning("SKILL.md YAML frontmatter 未正确关闭: %s", skill_file)
        return None

    try:
        raw = _load_yaml(rest[: closing.start()])
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
    if not resolved.is_relative_to(scan_root):
        logger.warning("SKILL.md 经符号链接指向扫描根之外，跳过: %s -> %s", skill_file, resolved)
        return None
    return Skill(
        name=name,
        description=description,
        location=resolved,
        source_path=resolved.parent,
        body=rest[closing.end() :].strip(),
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

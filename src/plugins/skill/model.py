"""Skill 数据模型（CONTEXT 术语：Skill——YAML frontmatter 元数据 + Markdown 正文）。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Skill(BaseModel):
    """一个 SKILL.md 的解析结果（issue #62）。

    Attributes:
        name: 唯一标识（frontmatter 必填）
        description: 简短描述（frontmatter 必填），进 prompt section
        location: SKILL.md 文件绝对路径（prompt section 的 location 字段，本票保证可读）
        source_path: SKILL.md 所在目录绝对路径——加载结果返回它以支持引用 skill 附带文件（ADR 0004 Layer 3）
        body: frontmatter 之后的 Markdown 正文，按需加载，不注入 prompt
    """

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    location: Path
    source_path: Path
    body: str

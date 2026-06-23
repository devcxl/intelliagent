"""Skill 数据模型。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class SkillFrontmatter(BaseModel):
    """Skill YAML frontmatter 的结构化表示。

    Attributes:
        name: 唯一标识（必填）
        description: 简短描述，Layer 1 展示给模型（必填）
        license: 许可证（可选）
        compatibility: 兼容性标记（可选）
        metadata: 扩展元数据（可选）
    """

    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillDef(BaseModel):
    """完整的 Skill 定义。

    Attributes:
        frontmatter: YAML frontmatter 的结构化数据
        body: frontmatter 之后的全部 Markdown 内容
        source_path: SKILL.md 所在目录的绝对路径（Layer 3 引用文件时使用）
    """

    frontmatter: SkillFrontmatter
    body: str
    source_path: Path

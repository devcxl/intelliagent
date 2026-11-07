"""会话列表的视图模型（ADR 0013）：TUI 只依赖这个 DTO，不感知存储实现。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SessionSummary:
    """会话列表一项：id、可选标题与创建时间，供选择器渲染。"""

    entry_id: str
    title: str | None
    created_at: datetime

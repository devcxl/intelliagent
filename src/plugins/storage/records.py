"""存储层记录模型：Entry / MessagePayload / CompactionRecord / RunRecord / Projection（CONTEXT 术语表）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.plugins.storage.errors import StorageError

ENTRY_TYPE_CONVERSATION = "conversation"
ENTRY_TYPE_MESSAGE = "message"
ENTRY_TYPE_COMPACTION = "compaction"
ENTRY_TYPE_RUN = "run"
ENTRY_TYPE_RUN_STATUS = "run_status"


class Entry(BaseModel):
    """一条 append-only 记录（CONTEXT 术语：Message / Compaction / Run 的落库抽象）。"""

    model_config = ConfigDict(frozen=True)

    id: str
    parent_id: str | None = None
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class MessagePayload(BaseModel):
    """message entry 的 payload：Conversation/Message 经 entry 抽象落库，不设平行的可变消息表。"""

    model_config = ConfigDict(frozen=True)

    role: str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_args: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class CompactionRecord(BaseModel):
    """compaction 记录（CONTEXT 术语：Compaction）：摘要 + 保留切点 + prompt checkpoint。"""

    model_config = ConfigDict(frozen=True)

    entry_id: str
    summary: str
    first_kept_entry_id: str
    prompt_checkpoint: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @classmethod
    def from_entry(cls, entry: Entry) -> CompactionRecord:
        """从 compaction entry 还原记录；payload 不完整时报可诊断错误。"""
        if entry.type != ENTRY_TYPE_COMPACTION:
            raise StorageError(f"entry '{entry.id}' is not a compaction entry (type '{entry.type}')")
        try:
            return cls(
                entry_id=entry.id,
                summary=entry.payload["summary"],
                first_kept_entry_id=entry.payload["first_kept_entry_id"],
                prompt_checkpoint=entry.payload["prompt_checkpoint"],
                created_at=entry.created_at,
            )
        except (KeyError, TypeError, ValidationError) as exc:
            raise StorageError(f"compaction entry '{entry.id}' has a malformed payload: {exc}") from exc


class RunRecord(BaseModel):
    """一次 Engine 执行的元数据投影：状态与 token 统计由追加的 run_status entry 现算（CONTEXT 术语：Run）。"""

    model_config = ConfigDict(frozen=True)

    run_id: str
    status: str
    model: str | None = None
    token_usage: dict[str, int] | None = None
    created_at: datetime
    updated_at: datetime


class Projection(BaseModel):
    """发给模型的上下文视图（CONTEXT 术语：Projection）：compaction 摘要 + 保留段 entry 序列。"""

    model_config = ConfigDict(frozen=True)

    compaction: CompactionRecord | None = None
    entries: tuple[Entry, ...] = ()

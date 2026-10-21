"""storage 内置插件（ADR 0007 / ADR 0010）：SQLite 承载 append-only entry 语义的 STORAGE 能力。"""

from src.plugins.storage.errors import EntryNotFoundError, StorageError
from src.plugins.storage.plugin import STORAGE_CAPABILITY_NAME, StorageConfig, StoragePlugin
from src.plugins.storage.records import (
    ENTRY_TYPE_COMPACTION,
    ENTRY_TYPE_MESSAGE,
    ENTRY_TYPE_RUN,
    ENTRY_TYPE_RUN_STATUS,
    CompactionRecord,
    Entry,
    MessagePayload,
    Projection,
    RunRecord,
)
from src.plugins.storage.store import StorageStore

__all__ = [
    "ENTRY_TYPE_COMPACTION",
    "ENTRY_TYPE_MESSAGE",
    "ENTRY_TYPE_RUN",
    "ENTRY_TYPE_RUN_STATUS",
    "STORAGE_CAPABILITY_NAME",
    "CompactionRecord",
    "Entry",
    "EntryNotFoundError",
    "MessagePayload",
    "Projection",
    "RunRecord",
    "StorageConfig",
    "StorageError",
    "StoragePlugin",
    "StorageStore",
]

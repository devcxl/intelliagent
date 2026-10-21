"""存储层错误：append-only 语义与 entry 链完整性相关的失败。"""

from __future__ import annotations


class StorageError(Exception):
    """存储层错误基类。"""


class EntryNotFoundError(StorageError):
    """引用的 entry 不存在（parent 链断裂或 compaction 切点缺失）。"""

"""core 测试夹具：compaction 测试用的 tmp_path SQLite 存储（镜像 tests/plugins/storage/conftest.py）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from src.plugins.storage import StorageStore


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[StorageStore]:
    instance = StorageStore(str(tmp_path / "storage.db"))
    await instance.initialize()
    try:
        yield instance
    finally:
        await instance.close()

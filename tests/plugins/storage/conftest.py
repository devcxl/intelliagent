"""storage 存储层测试夹具：每个测试一个 tmp_path SQLite 文件库。"""

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

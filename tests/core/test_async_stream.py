"""同步→异步桥的顺序、异常与提前退出语义（引擎增量渲染依赖它的正确性）。"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator

import pytest

from src.core.async_stream import iterate_in_thread

WAIT_LIMIT = 100


async def test_items_keep_source_order() -> None:
    """逐项产出且顺序不变。"""
    items = [item async for item in iterate_in_thread(iter([1, 2, 3]))]
    assert items == [1, 2, 3]


async def test_source_exception_is_raised_after_delivered_items() -> None:
    """生产端异常按原顺序在消费端重新抛出，不吞掉已产出的项。"""

    def source() -> Iterator[int]:
        yield 1
        raise RuntimeError("boom")

    items: list[int] = []
    with pytest.raises(RuntimeError, match="boom"):
        async for item in iterate_in_thread(source()):
            items.append(item)
    assert items == [1]


async def test_consumer_break_closes_source() -> None:
    """消费端提前退出时关闭源迭代器（provider 的 HTTP 流不会被遗弃）。"""
    closed = threading.Event()

    def source() -> Iterator[int]:
        try:
            yield 1
            yield 2
        finally:
            closed.set()

    async for _item in iterate_in_thread(source()):
        break
    for _ in range(WAIT_LIMIT):
        if closed.is_set():
            break
        await asyncio.sleep(0.01)
    assert closed.is_set()

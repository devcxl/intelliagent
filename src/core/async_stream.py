"""同步迭代器的异步桥：让同步阻塞的 LLM 流不再占住 asyncio 事件循环。

provider SDK（OpenAI / Anthropic）的流式接口是同步迭代器。若在 asyncio 任务里直接迭代，
网络等待会阻塞整个事件循环：TUI 在整段响应期间无法重绘，只能在收束后一次性看到内容。

本模块用 daemon 线程拉取同步迭代器，事件经线程安全队列回到事件循环，顺序不变；
消费端取消时后台线程会在下一次拿到数据后自行收束，不把异常或资源泄漏留给调用方。
队列不设上限：单个响应的增量数量受模型输出上限约束；引擎消费速度快于网络到达速度。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import TypeVar, cast

T = TypeVar("T")


class _End:
    """流结束哨兵（与任何合法事件区分）。"""


_END = _End()


@dataclass(frozen=True)
class _Failure:
    """后台线程的异常：在事件循环线程上按原顺序重新抛出。"""

    error: BaseException


async def iterate_in_thread(iterable: Iterable[T]) -> AsyncIterator[T]:
    """在 daemon 线程迭代同步 iterable，逐项产出到事件循环；生产端异常原样转交。

    顺序由单生产者/单消费者保证。消费端提前退出（取消/break）时设置停止标志，
    后台线程在下一项到达后关闭源迭代器并退出。
    """
    loop = asyncio.get_running_loop()
    items: asyncio.Queue[object] = asyncio.Queue()
    stopped = threading.Event()

    def deliver(item: object) -> None:
        if stopped.is_set():
            return
        try:
            loop.call_soon_threadsafe(items.put_nowait, item)
        except RuntimeError:  # 事件循环已关闭：消费端不在了
            stopped.set()

    def produce() -> None:
        try:
            for item in iterable:
                deliver(item)
                if stopped.is_set():
                    break
        except BaseException as error:  # noqa: BLE001 - 原样转交，由消费端决定语义
            deliver(_Failure(error))
        else:
            deliver(_END)
        finally:
            stopped.set()
            close = getattr(iterable, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # 清理失败不覆盖已产生的流结果或异常
                    pass

    threading.Thread(target=produce, name="intelliagent-stream", daemon=True).start()
    try:
        while True:
            item = await items.get()
            if item is _END:
                return
            if isinstance(item, _Failure):
                raise item.error
            yield cast(T, item)
    finally:
        stopped.set()

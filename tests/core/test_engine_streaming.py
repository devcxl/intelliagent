"""引擎流式消费不阻塞事件循环：同步 LLM 流在后台线程迭代（TUI 增量渲染的前提）。

真实 provider SDK 的 stream 是同步迭代器；若在 asyncio 任务里直接迭代，整段响应期间事件循环
被占住，前端只能在收束后一次性看到内容。本测试用"首个增量后阻塞"的 fake 钉死该行为。
"""

from __future__ import annotations

import asyncio

from src.core.agent_events import MessageUpdate
from src.llm.stream import TextDelta
from tests.core.engine_support import BLOCK_TIMEOUT_SECONDS, BlockingLLM, RecordingSink, build_engine


async def test_run_keeps_event_loop_responsive_while_stream_blocks() -> None:
    """第一个增量必须在流仍阻塞时送达 sink，且 run 不能已经收束。"""
    llm = BlockingLLM()
    sink = RecordingSink()
    engine = build_engine(llm, sink=sink)
    task = asyncio.create_task(engine.run("task"))
    try:
        for _ in range(200):
            if llm.first_chunk.is_set():
                break
            await asyncio.sleep(0.005)
        assert llm.first_chunk.is_set(), "LLM stream did not start"
        assert not task.done(), "run finished before the stream was released"
        deltas = [
            event.delta.text
            for event in sink.events
            if isinstance(event, MessageUpdate) and isinstance(event.delta, TextDelta)
        ]
        assert deltas == ["first"], "first delta was not delivered while the stream was blocked"
    finally:
        llm.release.set()
        await asyncio.wait_for(task, timeout=BLOCK_TIMEOUT_SECONDS)

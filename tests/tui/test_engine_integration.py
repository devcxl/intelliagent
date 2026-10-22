"""端到端：真实 Engine（fake LLM）的事件流驱动 TUI——仅消费事件流（issue #61 验收）。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.core.agent_events import EventSink
from src.core.engine import Engine
from src.tui.app import IntelliAgentApp
from src.tui.editor import PromptEditor
from src.tui.message_stream import MessageStream
from src.tui.message_view import MessageView
from src.tui.widgets import StatusBar, ToolCallPanel
from tests.core.engine_support import (
    BlockingLLM,
    FakeLLM,
    build_engine,
    make_tool,
    text_events,
    tool_arguments,
    tool_call_events,
)
from tests.tui.conftest import submit


async def test_engine_run_renders_through_event_stream() -> None:
    llm = FakeLLM()
    llm.enqueue(*tool_call_events([("call_1", "rec", tool_arguments("a.txt"))]))
    llm.enqueue(*text_events("all done"))
    log: list[str] = []
    tool = make_tool(log)

    def factory(sink: EventSink) -> Engine:
        return build_engine(llm, tools=[tool], sink=sink)

    app = IntelliAgentApp(runner_factory=factory, model="fake/model", cwd=Path("/work"))
    async with app.run_test() as pilot:
        await submit(pilot, "run it")
        children = list(app.query_one(MessageStream).children)
        assert [type(child).__name__ for child in children] == [
            "MessageView",
            "MessageView",
            "ToolCallPanel",
            "MessageView",
        ]
        assert [child.text for child in children if isinstance(child, MessageView)] == ["run it", "", "all done"]
        panel = children[2]
        assert isinstance(panel, ToolCallPanel)
        assert "成功" in panel.title
        assert "已完成" in app.query_one(StatusBar).text
        assert log == ["execute:rec"]


async def test_deltas_render_while_engine_stream_is_blocked() -> None:
    """同步 LLM 流阻塞时界面仍能增量渲染：提交后先看到首个 delta，而不是等整段响应收束。"""
    llm = BlockingLLM()

    def factory(sink: EventSink) -> Engine:
        return build_engine(llm, sink=sink)

    app = IntelliAgentApp(runner_factory=factory, model="fake/model", cwd=Path("/work"))
    async with app.run_test() as pilot:
        prompt = app.query_one("#prompt", PromptEditor)
        prompt.text = "stream it"
        await pilot.press("enter")
        try:
            for _ in range(200):
                if llm.first_chunk.is_set():
                    break
                await asyncio.sleep(0.005)
            assert llm.first_chunk.is_set(), "LLM stream did not start"
            assistant = list(app.query_one(MessageStream).query(MessageView))[-1]
            for _ in range(100):
                if assistant.rendered_text == "first":
                    break
                await pilot.pause()
            assert assistant.rendered_text == "first", "first delta was not rendered while the stream was blocked"
        finally:
            llm.release.set()
            await app.workers.wait_for_complete()
            await pilot.pause()
        assert assistant.rendered_text == "firstsecond"

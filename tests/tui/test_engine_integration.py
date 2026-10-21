"""端到端：真实 Engine（fake LLM）的事件流驱动 TUI——仅消费事件流（issue #61 验收）。"""

from __future__ import annotations

from pathlib import Path

from src.core.agent_events import EventSink
from src.core.engine import Engine
from src.tui.app import IntelliAgentApp
from src.tui.widgets import MessageStream, MessageView, StatusBar, ToolCallPanel
from tests.core.engine_support import FakeLLM, build_engine, make_tool, text_events, tool_call_events, tool_arguments
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

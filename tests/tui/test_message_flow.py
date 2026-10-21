"""消息流渲染：用户/助手消息按事件顺序出现（issue #61 验收）。"""

from __future__ import annotations

from src.core.agent_events import AgentEnd, AgentStart, MessageEnd, MessageStart, MessageUpdate
from src.llm.stream import TextDelta
from src.tui.widgets import MessageStream, MessageView
from tests.tui.conftest import make_app, submit


async def test_submit_renders_user_message_and_engine_message() -> None:
    app, runner = make_app()
    runner.enqueue(
        AgentStart(),
        MessageStart("m1", role="assistant"),
        MessageUpdate("m1", TextDelta("你好，")),
        MessageUpdate("m1", TextDelta("世界")),
        MessageEnd("m1"),
        AgentEnd("settled"),
    )
    async with app.run_test() as pilot:
        await submit(pilot, "做个测试")
        views = list(app.query_one(MessageStream).query(MessageView))
        assert [view.text for view in views] == ["做个测试", "你好，世界"]
        assert [view.role for view in views] == ["user", "assistant"]


async def test_messages_accumulate_across_runs() -> None:
    app, runner = make_app()
    runner.enqueue(MessageStart("m1"), MessageUpdate("m1", TextDelta("一")), MessageEnd("m1"))
    runner.enqueue(MessageStart("m2"), MessageUpdate("m2", TextDelta("二")), MessageEnd("m2"))
    async with app.run_test() as pilot:
        await submit(pilot, "任务一")
        await submit(pilot, "任务二")
        texts = [view.text for view in app.query_one(MessageStream).query(MessageView)]
        assert texts == ["任务一", "一", "任务二", "二"]

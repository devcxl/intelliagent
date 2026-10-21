"""输入提交：多行编辑器提交触发 Engine.run（issue #61 验收）。"""

from __future__ import annotations

import asyncio

from textual.widgets import TextArea

from src.tui.widgets import MessageStream, MessageView
from tests.tui.conftest import make_app, submit


async def test_editor_accepts_multi_line_typing_and_submits() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        prompt = pilot.app.query_one("#prompt", TextArea)
        prompt.focus()
        await pilot.press("a", "enter", "b")
        assert prompt.text == "a\nb"
        await pilot.press("ctrl+j")
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert runner.tasks == ["a\nb"]


async def test_submit_renders_user_message_and_clears_editor() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        await submit(pilot, "line1\nline2")
        assert runner.tasks == ["line1\nline2"]
        assert pilot.app.query_one("#prompt", TextArea).text == ""
        texts = [view.text for view in app.query_one(MessageStream).query(MessageView)]
        assert texts == ["line1\nline2"]


async def test_blank_submit_is_ignored() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        await submit(pilot, "   ")
        assert runner.tasks == []
        assert list(app.query_one(MessageStream).query(MessageView)) == []


async def test_submit_while_running_is_steered() -> None:
    app, runner = make_app()
    runner.gate = asyncio.Event()
    async with app.run_test() as pilot:
        prompt = pilot.app.query_one("#prompt", TextArea)
        prompt.focus()
        prompt.load_text("first task")
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert runner.tasks == ["first task"]
        prompt.load_text("steering note")
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert runner.tasks == ["first task"]
        assert runner.steered == ["steering note"]
        runner.gate.set()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()

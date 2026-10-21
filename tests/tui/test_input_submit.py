"""输入提交：单行输入框 Enter 提交触发 Engine.run（issue #61 验收）。"""

from __future__ import annotations

import asyncio

from textual.widgets import Input

from src.tui.widgets import MessageStream, MessageView
from tests.tui.conftest import make_app, submit


async def test_input_accepts_text_and_submits_on_enter() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        prompt = pilot.app.query_one("#prompt", Input)
        prompt.focus()
        await pilot.press("h", "i")
        assert prompt.value == "hi"
        await pilot.press("enter")
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert runner.tasks == ["hi"]


async def test_submit_renders_user_message_and_clears_editor() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        await submit(pilot, "hello world")
        assert runner.tasks == ["hello world"]
        assert pilot.app.query_one("#prompt", Input).value == ""
        texts = [view.text for view in app.query_one(MessageStream).query(MessageView)]
        assert texts == ["hello world"]


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
        prompt = pilot.app.query_one("#prompt", Input)
        prompt.focus()
        prompt.value = "first task"
        await pilot.press("enter")
        await pilot.pause()
        assert runner.tasks == ["first task"]
        prompt.value = "steering note"
        await pilot.press("enter")
        await pilot.pause()
        assert runner.tasks == ["first task"]
        assert runner.steered == ["steering note"]
        runner.gate.set()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()


class TestReviewRegressions:
    """PR #76 审查回归：steering 收束窗口语义。"""

    async def test_submit_in_settle_window_goes_to_follow_up(self) -> None:
        """引擎已收束（agent_end 已发）而 worker 未回收的窗口期提交转 follow_up，不再静默丢失。"""
        from src.core.agent_events import AgentEnd

        app, runner = make_app()
        runner.gate = asyncio.Event()
        async with app.run_test() as pilot:
            prompt = pilot.app.query_one("#prompt", Input)
            prompt.focus()
            prompt.value = "first task"
            await pilot.press("enter")
            await pilot.pause()
            runner.sink.emit(AgentEnd(outcome="settled"))  # 引擎收束，worker 仍挂起
            await pilot.pause()
            prompt.value = "late message"
            await pilot.press("enter")
            await pilot.pause()
            assert runner.follow_ups == ["late message"]
            assert runner.steered == []
            runner.gate.set()
            await pilot.app.workers.wait_for_complete()

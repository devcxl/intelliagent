"""多行编辑器与 pi 键位：换行/提交/中止/退出/历史/自适应高度（issue #89 验收）。

键位断言一律走 Textual Pilot 按键，读的是界面可观察状态（编辑器文本、高度、状态栏、
runner 收到的信号），不调用编辑器私有方法。
"""

from __future__ import annotations

import asyncio

from textual.pilot import Pilot

from src.core.agent_events import AgentEnd, AgentStart
from src.tui.editor import MAX_HEIGHT, MAX_HISTORY, MIN_HEIGHT, PromptEditor
from src.tui.message_stream import MessageStream
from src.tui.message_view import MessageView
from src.tui.widgets import StatusBar
from tests.tui.conftest import make_app, submit


def editor(pilot: Pilot) -> PromptEditor:
    return pilot.app.query_one("#prompt", PromptEditor)


async def test_placeholder_documents_submit_and_newline_keys() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        placeholder = str(editor(pilot).placeholder)
        assert "Enter 提交" in placeholder
        assert "Shift+Enter" in placeholder


async def test_shift_enter_and_ctrl_j_insert_newlines_without_submitting() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        await pilot.press("a", "shift+enter", "b", "ctrl+j", "c")
        await pilot.pause()
        assert editor(pilot).text == "a\nb\nc"
        assert runner.tasks == []


async def test_enter_submits_multiline_text() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        await submit(pilot, "first line\nsecond line")
        assert runner.tasks == ["first line\nsecond line"]
        views = list(app.query_one(MessageStream).query(MessageView))
        assert [view.text for view in views] == ["first line\nsecond line"]


async def test_submit_preserves_original_whitespace() -> None:
    """提交不裁剪：缩进、行尾空格与末尾换行原样交给 runner、消息视图与历史。"""
    raw = "  indented\ncode  \n"
    app, runner = make_app()
    async with app.run_test() as pilot:
        await submit(pilot, raw)
        assert runner.tasks == [raw]
        views = list(app.query_one(MessageStream).query(MessageView))
        assert [view.text for view in views] == [raw]
        await pilot.press("ctrl+p")
        await pilot.pause()
        assert editor(pilot).text == raw


async def test_wrapped_long_line_drives_height_and_resizes() -> None:
    """软换行按可视行数驱动高度：窄终端增高并封顶，清空回落，resize 后按新宽度重算。"""
    app, _ = make_app()
    async with app.run_test(size=(40, 24)) as pilot:
        prompt = editor(pilot)
        prompt.text = "word " * 80
        await pilot.pause()
        assert prompt.size.height == MAX_HEIGHT

        await pilot.press("ctrl+c")
        await pilot.pause()
        assert prompt.size.height == MIN_HEIGHT

        prompt.text = "word " * 80
        await pilot.pause()
        assert prompt.size.height == MAX_HEIGHT
        await pilot.resize_terminal(200, 24)
        await pilot.pause()
        assert MIN_HEIGHT <= prompt.size.height < MAX_HEIGHT


async def test_editor_height_grows_between_min_and_max_then_resets() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        prompt = editor(pilot)
        await pilot.pause()
        assert prompt.size.height == MIN_HEIGHT
        await pilot.press("a", "shift+enter", "shift+enter", "shift+enter", "b")
        await pilot.pause()
        assert prompt.text == "a\n\n\nb"
        assert prompt.size.height == 4
        for _ in range(6):
            await pilot.press("shift+enter")
        await pilot.pause()
        assert prompt.size.height == MAX_HEIGHT
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert prompt.text == ""
        assert prompt.size.height == MIN_HEIGHT


async def test_escape_while_idle_has_no_side_effect() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
        assert runner.abort_events == []
        assert runner.tasks == []
        assert "就绪" in app.query_one(StatusBar).text
        assert app.is_running


async def test_escape_sets_abort_signal_and_reports_aborting_then_aborted() -> None:
    app, runner = make_app()
    runner.gate = asyncio.Event()
    runner.enqueue(AgentStart())
    async with app.run_test() as pilot:
        prompt = editor(pilot)
        prompt.text = "long task"
        await pilot.press("enter")
        await pilot.pause()
        assert "运行中" in app.query_one(StatusBar).text

        await pilot.press("escape")
        await pilot.pause()
        assert len(runner.abort_events) == 1
        assert runner.abort_events[0].is_set()
        assert "中止中" in app.query_one(StatusBar).text

        runner.gate.set()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()
        assert "已中止" in app.query_one(StatusBar).text


async def test_escape_in_settle_window_keeps_final_state() -> None:
    """agent_end 已发、worker 未回收时 Esc 不再置位中止，也不把最终状态改回「中止中」。"""
    app, runner = make_app()
    runner.gate = asyncio.Event()
    runner.enqueue(AgentStart())
    async with app.run_test() as pilot:
        prompt = editor(pilot)
        prompt.text = "task"
        await pilot.press("enter")
        await pilot.pause()
        runner.sink.emit(AgentEnd(outcome="settled"))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert not runner.abort_events[0].is_set()
        assert "已完成" in app.query_one(StatusBar).text
        runner.gate.set()
        await pilot.app.workers.wait_for_complete()
        await pilot.pause()


async def test_ctrl_c_copies_selection_without_clearing() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        await pilot.press("a", "b", "c", "f7")
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert app.clipboard == "abc"
        assert editor(pilot).text == "abc"


async def test_ctrl_c_clears_non_empty_editor() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        await pilot.press("a", "b", "c")
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert editor(pilot).text == ""
        assert app.is_running


async def test_ctrl_c_exits_when_editor_is_empty() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+c")
        await pilot.pause()
        assert not app.is_running


async def test_ctrl_d_deletes_right_character_when_non_empty() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        await pilot.press("a", "b", "c", "home")
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert editor(pilot).text == "bc"
        assert app.is_running


async def test_ctrl_d_exits_when_editor_is_empty() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert not app.is_running


async def test_ctrl_q_quits_immediately() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        await pilot.press("ctrl+q")
        await pilot.pause()
        assert not app.is_running


async def test_ctrl_p_and_ctrl_n_browse_prompt_history() -> None:
    app, runner = make_app()
    async with app.run_test() as pilot:
        await submit(pilot, "first prompt")
        await submit(pilot, "second prompt")
        await pilot.press("ctrl+p")
        await pilot.pause()
        assert editor(pilot).text == "second prompt"
        await pilot.press("ctrl+p")
        await pilot.pause()
        assert editor(pilot).text == "first prompt"
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert editor(pilot).text == "second prompt"
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert editor(pilot).text == ""
        assert runner.tasks == ["first prompt", "second prompt"]


async def test_history_keeps_recent_hundred_entries() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        prompt = editor(pilot)
        for index in range(MAX_HISTORY + 5):
            prompt.remember(f"prompt {index}")
        assert len(prompt.prompt_history) == MAX_HISTORY
        assert prompt.prompt_history[-1] == f"prompt {MAX_HISTORY + 4}"
        assert prompt.prompt_history[0] == "prompt 5"

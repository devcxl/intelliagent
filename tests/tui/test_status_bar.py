"""状态栏：运行状态与耗时、模型、本轮 token、目录缩略（issue #90 验收）。

计时断言注入可推进的时钟，读取状态栏公开文本；不依赖真实每秒等待。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.agent_events import AgentEnd, AgentStart, MessageEnd, MessageStart, RunOutcome
from src.llm.stream import Usage
from src.tui.widgets import StatusBar
from tests.tui.conftest import FakeClock, make_app


async def test_status_bar_shows_cwd_model_and_state() -> None:
    app, _ = make_app(model="fake/model", cwd=Path("/work/project"))
    async with app.run_test() as pilot:
        bar = pilot.app.query_one(StatusBar)
        assert "/work/project" in bar.text
        assert "fake/model" in bar.text
        assert "就绪" in bar.text
        assert "tok" not in bar.text


@pytest.mark.parametrize(
    ("outcome", "label"),
    [("settled", "已完成"), ("terminated", "已终止"), ("error", "出错"), ("aborted", "已中止")],
)
async def test_status_bar_follows_run_state(outcome: RunOutcome, label: str) -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        bar = pilot.app.query_one(StatusBar)
        app.event_sink.emit(AgentStart())
        await pilot.pause()
        assert "运行中" in bar.text
        app.event_sink.emit(AgentEnd(outcome))
        await pilot.pause()
        assert label in bar.text


async def test_status_bar_counts_seconds_then_keeps_final_elapsed() -> None:
    """运行中按秒推进；收束后冻结最终耗时；下一次 run 重新从 0 计时。"""
    clock = FakeClock()
    app, _ = make_app(clock=clock)
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        app.event_sink.emit(AgentStart())
        await pilot.pause()
        assert "运行中 0s" in bar.text

        clock.advance(3)
        assert "运行中 3s" in bar.text

        app.event_sink.emit(AgentEnd("settled"))
        await pilot.pause()
        assert "已完成 3s" in bar.text

        clock.advance(10)
        assert "已完成 3s" in bar.text

        app.event_sink.emit(AgentStart())
        await pilot.pause()
        assert "运行中 0s" in bar.text


async def test_status_bar_shows_usage_tokens_and_resets_on_new_run() -> None:
    """收到带 usage 的 MessageEnd 后显示本轮输入/输出 token；新 run 清空旧值。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        app.event_sink.emit(AgentStart())
        app.event_sink.emit(MessageStart("m1"))
        app.event_sink.emit(MessageEnd("m1", usage=Usage(prompt_tokens=1200, completion_tokens=300, total_tokens=1500)))
        await pilot.pause()
        assert "tok ↑1.2k ↓300" in bar.text

        app.event_sink.emit(AgentEnd("settled"))
        await pilot.pause()
        assert "↑1.2k" in bar.text

        app.event_sink.emit(AgentStart())
        await pilot.pause()
        assert "tok" not in bar.text


async def test_status_bar_without_usage_keeps_token_segment_hidden() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        bar = app.query_one(StatusBar)
        app.event_sink.emit(AgentStart())
        app.event_sink.emit(MessageStart("m1"))
        app.event_sink.emit(MessageEnd("m1", usage=None))
        await pilot.pause()
        assert "tok" not in bar.text


async def test_status_bar_collapses_home_prefix_to_tilde() -> None:
    cwd = Path.home() / "projects" / "demo"
    app, _ = make_app(cwd=cwd)
    async with app.run_test():
        bar = app.query_one(StatusBar)
        assert "~/projects/demo" in bar.text
        assert str(Path.home()) not in bar.text

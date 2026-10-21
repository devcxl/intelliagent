"""状态栏：工作目录、模型、运行状态（issue #61 验收）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.agent_events import AgentEnd, AgentStart, RunOutcome
from src.tui.widgets import StatusBar
from tests.tui.conftest import make_app


async def test_status_bar_shows_cwd_model_and_state() -> None:
    app, _ = make_app(model="fake/model", cwd=Path("/work/project"))
    async with app.run_test() as pilot:
        bar = pilot.app.query_one(StatusBar)
        assert "/work/project" in bar.text
        assert "fake/model" in bar.text
        assert "就绪" in bar.text


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

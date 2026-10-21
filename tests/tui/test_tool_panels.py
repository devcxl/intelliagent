"""工具调用折叠面板：执行中态 → 最终结果，折叠/展开可切换（issue #61 验收）。"""

from __future__ import annotations

import pytest

from src.core.agent_events import ToolExecutionEnd, ToolExecutionStart
from src.core.tool_pipeline import Observation, ObservationStatus
from src.tui.widgets import ToolCallPanel
from tests.tui.conftest import make_app


def observation(status: ObservationStatus, content: str = "文件内容", error: str | None = None) -> Observation:
    return Observation(
        tool_call_id="call_1",
        name="read",
        arguments={"path": "a.txt"},
        content=content,
        status=status,
        error=error,
    )


async def test_tool_panel_running_state_then_success() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        await pilot.pause()
        panel = app.query_one(ToolCallPanel)
        assert panel.collapsed is True
        assert "read" in panel.title
        assert "执行中" in panel.title
        app.event_sink.emit(ToolExecutionEnd("call_1", observation("success")))
        await pilot.pause()
        assert "成功" in panel.title
        assert "文件内容" in panel.body_text
        assert "a.txt" in panel.body_text


async def test_tool_panel_toggles_with_enter() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        await pilot.pause()
        panel = app.query_one(ToolCallPanel)
        panel.focus()
        await pilot.press("enter")
        assert panel.collapsed is False
        await pilot.press("enter")
        assert panel.collapsed is True


@pytest.mark.parametrize(
    ("status", "label", "error"),
    [("error", "失败", "boom"), ("denied", "已拒绝", "无权限")],
)
async def test_tool_panel_failure_states(status: ObservationStatus, label: str, error: str) -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "bash", {"command": "rm"}))
        app.event_sink.emit(ToolExecutionEnd("call_1", observation(status, content="", error=error)))
        await pilot.pause()
        panel = app.query_one(ToolCallPanel)
        assert label in panel.title
        assert error in panel.body_text

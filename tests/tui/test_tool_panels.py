"""工具调用面板：运行中展开、结束折叠、标题状态与耗时、正文限高滚动、Ctrl+O 整体切换（issue #90）。"""

from __future__ import annotations

import pytest
from textual.containers import VerticalScroll

from src.core.agent_events import ToolExecutionEnd, ToolExecutionStart
from src.core.tool_pipeline import Observation, ObservationStatus
from src.tui.widgets import MessageStream, ToolCallPanel
from tests.tui.conftest import make_app


def observation(
    status: ObservationStatus, content: str = "文件内容", error: str | None = None, duration_ms: float = 0.0
) -> Observation:
    return Observation(
        tool_call_id="call_1",
        name="read",
        arguments={"path": "a.txt"},
        content=content,
        status=status,
        error=error,
        duration_ms=duration_ms,
    )


def panels(app) -> list[ToolCallPanel]:
    return list(app.query(ToolCallPanel))


async def test_tool_panel_expands_while_running_then_collapses_with_status_and_duration() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        await pilot.pause()
        panel = app.query_one(ToolCallPanel)
        assert panel.collapsed is False
        assert "read" in panel.title
        assert "执行中" in panel.title

        app.event_sink.emit(ToolExecutionEnd("call_1", observation("success", duration_ms=1234)))
        await pilot.pause()
        assert panel.collapsed is True
        assert "成功" in panel.title
        assert "1.23s" in panel.title
        assert "文件内容" in panel.body_text
        assert "a.txt" in panel.body_text


async def test_tool_panel_shows_sub_second_duration_with_hundredths() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        app.event_sink.emit(ToolExecutionEnd("call_1", observation("success", duration_ms=12)))
        await pilot.pause()
        assert "0.01s" in app.query_one(ToolCallPanel).title


async def test_tool_panel_toggles_with_click_and_enter() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        await pilot.pause()
        panel = app.query_one(ToolCallPanel)
        title = panel.query_one("CollapsibleTitle")
        title.focus()
        await pilot.press("enter")
        assert panel.collapsed is True
        await pilot.click(title)
        assert panel.collapsed is False


async def test_tool_panel_body_is_capped_at_twenty_lines_and_scrolls_internally() -> None:
    """超长结果不顶走消息流：正文最高 20 行，内容在面板内滚动。"""
    long_content = "\n".join(f"line {index}" for index in range(80))
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        app.event_sink.emit(ToolExecutionEnd("call_1", observation("success", content=long_content, duration_ms=12)))
        await pilot.pause()
        panel = app.query_one(ToolCallPanel)
        panel.collapsed = False
        await pilot.pause()

        body = panel.query_one(".tool-body", VerticalScroll)
        assert body.size.height <= 20
        assert body.max_scroll_y > 0
        assert panel.size.height <= 22
        assert app.query_one(MessageStream).size.height > 0


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


async def test_ctrl_o_expands_everything_when_any_panel_is_collapsed() -> None:
    """混合状态按「存在折叠则全部展开」处理；全展开后再按一次全部折叠。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        for index in range(3):
            app.event_sink.emit(ToolExecutionStart(f"call_{index}", "read", {"path": f"{index}.txt"}))
        await pilot.pause()
        assert all(not panel.collapsed for panel in panels(app))

        panels(app)[1].collapsed = True
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert all(not panel.collapsed for panel in panels(app))

        await pilot.press("ctrl+o")
        await pilot.pause()
        assert all(panel.collapsed for panel in panels(app))

        panels(app)[0].collapsed = False
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        assert all(not panel.collapsed for panel in panels(app))


async def test_ctrl_o_expands_panels_that_collapsed_after_tool_finished() -> None:
    app, _ = make_app()
    async with app.run_test() as pilot:
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        app.event_sink.emit(ToolExecutionEnd("call_1", observation("success", duration_ms=20)))
        await pilot.pause()
        assert app.query_one(ToolCallPanel).collapsed is True

        await pilot.press("ctrl+o")
        await pilot.pause()
        assert app.query_one(ToolCallPanel).collapsed is False

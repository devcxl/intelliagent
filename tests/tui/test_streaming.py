"""流式增量渲染（issue #63）：delta 中途可见、合并重绘、错误/空态、工具三态、半程清算。

TDD 先行：本文件先于实现落地，红转绿即验收证据。测试走声明 seam——事件经 EventSink 进入，
渲染断言读 MessageView 的落屏状态（rendered_text），不碰组件内部实现。
"""

from __future__ import annotations

import pytest

from src.core.agent_events import (
    AgentEnd,
    AgentStart,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
)
from src.core.tool_pipeline import Observation, ObservationStatus
from src.llm.stream import Error, TextDelta, ToolCallDelta
from src.tui.widgets import MessageStream, MessageView, StatusBar, ToolCallPanel
from tests.tui.conftest import make_app, submit


def observation(status: ObservationStatus, content: str = "ok", error: str | None = None) -> Observation:
    return Observation(
        tool_call_id="call_1",
        name="bash",
        arguments={"command": "ls"},
        content=content,
        status=status,
        error=error,
    )


def count_redraws(view: MessageView, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """记录该消息单元的重绘（update 调用）次数：验证合并重绘与不全量重绘。"""
    redraws: list[str] = []
    original = view.update

    def counting_update(content: object = "", *, layout: bool = True) -> None:
        redraws.append(str(content))
        original(content, layout=layout)

    monkeypatch.setattr(view, "update", counting_update)
    return redraws


async def test_delta_renders_before_message_end() -> None:
    """message_update 驱动增量渲染：不等 MessageEnd，每个增量中途即落屏。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageUpdate("m1", TextDelta("你好")))
        await pilot.pause()
        view = app.query_one(MessageView)
        assert view.rendered_text == "你好"
        sink.emit(MessageUpdate("m1", TextDelta("，世界")))
        await pilot.pause()
        assert view.rendered_text == "你好，世界"
        sink.emit(MessageEnd("m1"))
        await pilot.pause()
        assert view.rendered_text == "你好，世界"


async def test_deltas_merge_into_single_redraw(monkeypatch: pytest.MonkeyPatch) -> None:
    """渲染成本控制：一轮到达的多个 delta 合并为一次重绘，且只重绘该消息单元（requestRender 语义）。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageStart("m2", role="assistant"))
        await pilot.pause()
        views = {view.message_id: view for view in app.query_one(MessageStream).query(MessageView)}
        redraws_m1 = count_redraws(views["m1"], monkeypatch)
        redraws_m2 = count_redraws(views["m2"], monkeypatch)
        for chunk in ("流", "式", "渲染"):
            sink.emit(MessageUpdate("m1", TextDelta(chunk)))
        await pilot.pause()
        assert views["m1"].rendered_text == "流式渲染"
        assert len(redraws_m1) == 1
        assert redraws_m2 == []


async def test_error_delta_renders_error_state() -> None:
    """错误态：流式错误随增量落屏，错误不被吞掉。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageUpdate("m1", TextDelta("已生成部分")))
        sink.emit(MessageUpdate("m1", Error("连接被重置")))
        await pilot.pause()
        view = app.query_one(MessageView)
        assert "已生成部分" in view.rendered_text
        assert "流式错误：连接被重置" in view.rendered_text
        sink.emit(MessageEnd("m1"))
        await pilot.pause()
        assert "流式错误：连接被重置" in view.rendered_text


async def test_empty_message_renders_placeholder() -> None:
    """空态：无任何增量即收束的消息显示占位；仅工具调用的消息不占位（信息在折叠面板）。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageStart("m2", role="assistant"))
        sink.emit(MessageUpdate("m2", ToolCallDelta(index=0, id="call_1", name="read", arguments_delta="{}")))
        sink.emit(MessageEnd("m1"))
        sink.emit(MessageEnd("m2"))
        await pilot.pause()
        views = {view.message_id: view for view in app.query_one(MessageStream).query(MessageView)}
        assert views["m1"].rendered_text == "（无内容）"
        assert views["m2"].rendered_text == ""


@pytest.mark.parametrize(("status", "label"), [("success", "成功"), ("error", "失败")])
async def test_tool_states_follow_events(status: ObservationStatus, label: str) -> None:
    """工具三态随 tool_execution 事件更新：执行中（含流式进度）→ 完成/失败。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(ToolExecutionStart("call_1", "bash", {"command": "ls"}))
        await pilot.pause()
        panel = app.query_one(ToolCallPanel)
        assert "执行中" in panel.title
        sink.emit(ToolExecutionUpdate("call_1", "扫描中"))
        await pilot.pause()
        assert "执行中" in panel.title
        assert "扫描中" in panel.body_text
        error = "boom" if status == "error" else None
        sink.emit(ToolExecutionEnd("call_1", observation(status, content="", error=error)))
        await pilot.pause()
        assert label in panel.title
        if error is not None:
            assert error in panel.body_text


async def test_half_message_flushed_when_run_settles_without_message_end() -> None:
    """半程清算：缺 MessageEnd 的消息在 run 收束时把缓冲增量落屏（PR #76 遗留）。"""
    app, runner = make_app()
    runner.enqueue(
        AgentStart(),
        MessageStart("m1", role="assistant"),
        MessageUpdate("m1", TextDelta("半程文本")),
        AgentEnd("error"),
    )
    async with app.run_test() as pilot:
        await submit(pilot, "任务")
        views = list(app.query_one(MessageStream).query(MessageView))
        assert views[1].text == "半程文本"
        assert views[1].rendered_text == "半程文本"


async def test_half_message_flushed_on_runner_exception() -> None:
    """半程清算（异常路径）：引擎异常缺 MessageEnd 时增量落屏，错误进消息流，状态栏出错。"""
    app, runner = make_app()
    runner.enqueue(
        AgentStart(),
        MessageStart("m1", role="assistant"),
        MessageUpdate("m1", TextDelta("半程文本")),
    )
    runner.raise_error = RuntimeError("引擎炸了")
    async with app.run_test() as pilot:
        await submit(pilot, "任务")
        views = list(app.query_one(MessageStream).query(MessageView))
        assert views[1].text == "半程文本"
        assert views[1].rendered_text == "半程文本"
        assert "运行异常" in views[-1].text
        assert "出错" in app.query_one(StatusBar).text

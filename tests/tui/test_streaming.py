"""流式增量渲染（issue #63）：delta 中途可见、合并重绘、错误/空态、工具三态、半程清算。

TDD 先行：本文件先于实现落地，红转绿即验收证据。测试走声明 seam——事件经 EventSink 进入，
渲染断言读 MessageView 的落屏状态（rendered_text），不碰组件内部实现。
"""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Markdown
from textual.widgets.markdown import MarkdownStream

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
from src.tui.message_stream import MessageStream
from src.tui.message_view import MessageView
from src.tui.widgets import StatusBar, ToolCallPanel
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


def spy_markdown_appends(view: MessageView, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """记录该消息的 Markdown 实际 append 片段：验证合并渲染与只重绘本单元。"""
    markdown = view.query_one(Markdown)
    appends: list[str] = []
    original = markdown.append

    def counting_append(fragment: str) -> object:
        appends.append(fragment)
        return original(fragment)

    monkeypatch.setattr(markdown, "append", counting_append)
    return appends


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
        assert view.query_one(Markdown).source == "你好"
        sink.emit(MessageUpdate("m1", TextDelta("，世界")))
        await pilot.pause()
        assert view.rendered_text == "你好，世界"
        assert view.query_one(Markdown).source == "你好，世界"
        sink.emit(MessageEnd("m1"))
        await pilot.pause()
        assert view.rendered_text == "你好，世界"


async def test_deltas_merge_into_single_redraw(monkeypatch: pytest.MonkeyPatch) -> None:
    """渲染成本控制：一轮到达的多个 delta 合并为一次 Markdown append，且只重绘本消息单元。

    成本约束由 Textual MarkdownStream 的排队合并保证；本测试只断言外部可见结果。
    """
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageStart("m2", role="assistant"))
        await pilot.pause()
        views = {view.message_id: view for view in app.query_one(MessageStream).query(MessageView)}
        appends_m1 = spy_markdown_appends(views["m1"], monkeypatch)
        appends_m2 = spy_markdown_appends(views["m2"], monkeypatch)
        for chunk in ("流", "式", "渲染"):
            sink.emit(MessageUpdate("m1", TextDelta(chunk)))
        await pilot.pause()
        assert views["m1"].rendered_text == "流式渲染"
        assert appends_m1 == ["流式渲染"]
        assert appends_m2 == []
        assert views["m1"].query_one(Markdown).source == "流式渲染"


async def test_start_and_deltas_in_one_sync_burst_are_not_lost() -> None:
    """MessageStart 与增量同一同步突发：挂载未完成时缓冲，流就绪后按序落屏。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageUpdate("m1", TextDelta("第一段")))
        sink.emit(MessageUpdate("m1", TextDelta("第二段")))
        await pilot.pause()
        view = app.query_one(MessageView)
        assert view.rendered_text == "第一段第二段"
        assert view.query_one(Markdown).source == "第一段第二段"


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


class TestReviewRegressions:
    """PR #78 审查回归：半程清算钉死（变异敏感）、合并机制钉死、空态占位边角。"""

    async def test_flush_pending_settles_message_without_message_end(self) -> None:
        """缺 MessageEnd 的空消息经清算落空态占位，而非裸角色标签（Standards medium）。"""
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            await pilot.pause()
            app._stream.flush_pending()  # 收束清算路径（异常/收束兜底）
            await pilot.pause()
            view = app.query_one(MessageView)
            assert view.rendered_text == "（无内容）"

    async def test_flush_pending_settles_message_started_in_same_burst(self) -> None:
        """同一同步突发里 Start 与收束事件到达：挂载未完成也要落空态占位，不丢半程消息。"""
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            sink.emit(AgentEnd("error"))
            await pilot.pause()
            view = app.query_one(MessageView)
            assert view.rendered_text == "（无内容）"

    async def test_settle_keeps_queued_text_when_consumer_has_not_run(self) -> None:
        """半程清算在消费者尚未运行时到达：已入队文本不丢，收束后正常落屏。"""
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            sink.emit(MessageUpdate("m1", TextDelta("half text")))
            app._stream.flush_pending()  # 不 pause：消费者尚未运行，清算必须保留已入队文本
            await pilot.pause()
            view = app.query_one(MessageView)
            assert view.rendered_text == "half text"
            assert view.stream_error is None

    async def test_sync_burst_renders_once_with_combined_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """同步突发的多个增量只产生一次 append，且片段是完整拼接。

        成本约束由队列消费者批量取走已入队片段 + MarkdownStream 自身的排队合并共同保证；
        这里只断言外部可见结果，不断言内部合并窗口。
        """
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            await pilot.pause()
            view = app.query_one(MessageView)
            appends = spy_markdown_appends(view, monkeypatch)
            sink.emit(MessageUpdate("m1", TextDelta("a")))
            sink.emit(MessageUpdate("m1", TextDelta("b")))
            sink.emit(MessageUpdate("m1", TextDelta("c")))
            await pilot.pause()
            assert appends == ["abc"]
            assert view.query_one(Markdown).source == "abc"

    async def test_delta_after_rendered_batch_still_renders(self) -> None:
        """一批增量渲染完之后到达的新增量仍按队列顺序继续落屏。"""
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            sink.emit(MessageUpdate("m1", TextDelta("a")))
            await pilot.pause()
            view = app.query_one(MessageView)
            assert view.rendered_text == "a"
            sink.emit(MessageUpdate("m1", TextDelta("b")))
            await pilot.pause()
            assert view.rendered_text == "ab"
            assert view.query_one(Markdown).source == "ab"

    async def test_late_delta_after_message_end_is_ignored(self) -> None:
        """MessageEnd 之后的晚到增量被拒绝：正文、Markdown.source 都不变，且不写已停止的流。"""
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            sink.emit(MessageUpdate("m1", TextDelta("before")))
            sink.emit(MessageEnd("m1"))
            await pilot.pause()
            view = app.query_one(MessageView)
            assert view.rendered_text == "before"

            sink.emit(MessageUpdate("m1", TextDelta("after")))
            await pilot.pause()
            assert view.text == "before"
            assert view.rendered_text == "before"
            assert view.query_one(Markdown).source == "before"
            assert view.stream_error is None

    async def test_unfinished_message_writer_is_stopped_on_app_exit(self) -> None:
        """未结束消息随应用退出收束：消费者任务不悬挂，Markdown 流停止且无未取回异常。"""
        before = set(asyncio.all_tasks())
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            sink.emit(MessageUpdate("m1", TextDelta("partial")))
            await pilot.pause()
            view = app.query_one(MessageView)
            assert view.rendered_text == "partial"

        pending = [task for task in asyncio.all_tasks() if task not in before and not task.done()]
        assert pending == []
        assert view.stream_error is None

    async def test_markdown_write_failure_is_recorded_not_unretrieved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """写入异常被消费者捕获并记录到 stream_error，不变成未取回的任务异常。"""

        async def failing_write(self: MarkdownStream, fragment: str) -> None:
            raise RuntimeError("markdown write failed")

        monkeypatch.setattr(MarkdownStream, "write", failing_write)
        app, _ = make_app()
        async with app.run_test() as pilot:
            sink = app.event_sink
            sink.emit(MessageStart("m1", role="assistant"))
            sink.emit(MessageUpdate("m1", TextDelta("正文")))
            await pilot.pause()
            view = app.query_one(MessageView)
            assert isinstance(view.stream_error, RuntimeError)
            assert "markdown write failed" in str(view.stream_error)

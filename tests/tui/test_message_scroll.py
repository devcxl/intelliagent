"""消息流滚动：贴底跟随、上滚停止、Ctrl+End 恢复、翻页/跳转键位（issue #91 验收）。

断言读公开滚动状态（scroll_y / max_scroll_y / is_vertical_scroll_end / following），
不依赖私有字段；键位走 Pilot，编辑器保持聚焦以验证 priority 绑定。
"""

from __future__ import annotations

from textual.pilot import Pilot

from src.core.agent_events import MessageStart, MessageUpdate, ToolExecutionEnd, ToolExecutionStart
from src.core.tool_pipeline import Observation
from src.llm.stream import TextDelta
from src.tui.editor import PromptEditor
from src.tui.message_stream import MessageStream
from src.tui.message_view import MessageView
from tests.tui.conftest import make_app


async def pause(pilot: Pilot, times: int = 3) -> None:
    for _ in range(times):
        await pilot.pause()


async def fill_stream(pilot: Pilot, count: int = 30) -> MessageStream:
    """填满消息流并等到贴底：返回可滚动的消息流容器。"""
    stream = pilot.app.query_one(MessageStream)
    for index in range(count):
        stream.add_message(MessageView("system", text=f"第 {index} 行"))
    await pause(pilot, 5)
    assert stream.max_scroll_y > 0
    assert stream.is_vertical_scroll_end
    return stream


async def test_at_bottom_follows_new_message_and_streaming_delta() -> None:
    """贴底时新消息与流式增量都自动滚到可见位置。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        stream = await fill_stream(pilot)
        assert stream.following

        stream.add_message(MessageView("system", text="新消息"))
        await pause(pilot)
        assert stream.is_vertical_scroll_end
        assert stream.following

        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageUpdate("m1", TextDelta("流式增量")))
        await pause(pilot, 5)
        assert stream.is_vertical_scroll_end
        assert stream.following


async def test_tool_panel_arrival_keeps_following() -> None:
    """工具面板插入消息流时同样保持贴底。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        stream = await fill_stream(pilot)
        app.event_sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        await pause(pilot)
        assert stream.is_vertical_scroll_end
        app.event_sink.emit(
            ToolExecutionEnd(
                "call_1",
                Observation(
                    tool_call_id="call_1",
                    name="read",
                    arguments={"path": "a.txt"},
                    content="done",
                    status="success",
                ),
            )
        )
        await pause(pilot)
        assert stream.is_vertical_scroll_end
        assert stream.following


async def test_scrolling_up_stops_following_without_moving_position() -> None:
    """用户上滚后停止跟随：新消息与增量都不再改变滚动位置。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        stream = await fill_stream(pilot)
        await pilot.press("pageup")
        await pause(pilot)
        assert not stream.is_vertical_scroll_end
        assert not stream.following
        scrolled_to = stream.scroll_y

        stream.add_message(MessageView("system", text="新消息不应拉回底部"))
        await pause(pilot)
        assert stream.scroll_y == scrolled_to
        assert not stream.following

        app.event_sink.emit(MessageStart("m1", role="assistant"))
        app.event_sink.emit(MessageUpdate("m1", TextDelta("新增量不应拉回底部")))
        await pause(pilot, 5)
        assert stream.scroll_y == scrolled_to
        assert not stream.following


async def test_ctrl_end_restores_following() -> None:
    """Ctrl+End 回到最新输出并恢复跟随：后续新内容继续自动贴底。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        stream = await fill_stream(pilot)
        await pilot.press("pageup")
        await pause(pilot)
        assert not stream.following

        await pilot.press("ctrl+end")
        await pause(pilot)
        assert stream.is_vertical_scroll_end
        assert stream.following

        stream.add_message(MessageView("system", text="恢复跟随后继续贴底"))
        await pause(pilot)
        assert stream.is_vertical_scroll_end
        assert stream.following


async def test_paging_keys_work_while_editor_has_focus() -> None:
    """PgUp/PgDn 是应用级 priority 绑定：编辑器聚焦时仍翻消息流，且不写入编辑器。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        stream = await fill_stream(pilot)
        prompt = app.query_one("#prompt", PromptEditor)
        prompt.focus()
        await pause(pilot)
        assert prompt.has_focus

        await pilot.press("pageup")
        await pause(pilot)
        assert not stream.is_vertical_scroll_end
        assert stream.scroll_y < stream.max_scroll_y
        assert prompt.text == ""
        assert prompt.has_focus

        await pilot.press("pagedown")
        await pause(pilot)
        assert stream.is_vertical_scroll_end
        assert stream.following
        assert prompt.has_focus


async def test_ctrl_home_jumps_to_top_and_does_not_move_editor_cursor() -> None:
    """Ctrl+Home 跳消息流顶部；编辑器聚焦时按键不被编辑器消费（光标不跳到文首）。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        stream = await fill_stream(pilot)
        prompt = app.query_one("#prompt", PromptEditor)
        prompt.focus()
        prompt.text = "abc"
        prompt.move_cursor(prompt.document.end)
        await pause(pilot)

        await pilot.press("ctrl+home")
        await pause(pilot)
        assert stream.scroll_y == 0
        assert not stream.following

        await pilot.press("x")
        await pause(pilot)
        assert prompt.text == "abcx"
        assert prompt.has_focus

        await pilot.press("ctrl+end")
        await pause(pilot)
        assert stream.is_vertical_scroll_end
        assert stream.following

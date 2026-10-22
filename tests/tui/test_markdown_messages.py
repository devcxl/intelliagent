"""消息展示：无角色前缀、assistant 的 Markdown 结构、user/system 的角色配色（issue #91 验收）。"""

from __future__ import annotations

from textual.color import Color
from textual.widgets import Markdown, Static

from src.core.agent_events import MessageEnd, MessageStart, MessageUpdate
from src.llm.stream import TextDelta
from src.tui.message_stream import MessageStream
from src.tui.message_view import MessageView
from tests.tui.conftest import make_app, submit

MARKDOWN_SOURCE = (
    "# 标题\n\n- 第一项\n- 第二项\n\n```python\nprint(1)\n```\n\n| 列一 | 列二 |\n| --- | --- |\n| 1 | 2 |\n"
)


async def stream_markdown(pilot, message_id: str = "m1", source: str = MARKDOWN_SOURCE) -> MessageView:
    """按小块把 Markdown 灌进一条 assistant 消息，等落屏后返回其消息单元。"""
    sink = pilot.app.event_sink
    sink.emit(MessageStart(message_id, role="assistant"))
    for index in range(0, len(source), 7):
        sink.emit(MessageUpdate(message_id, TextDelta(source[index : index + 7])))
    sink.emit(MessageEnd(message_id))
    views: list[MessageView] = []
    for _ in range(50):
        await pilot.pause()
        views = list(pilot.app.query(MessageView))
        if views and views[-1].rendered_text == source:
            break
    return views[-1]


async def test_assistant_renders_markdown_without_role_prefix() -> None:
    """assistant 无「助手」或任何前缀，正文按 Markdown 解析出标题、列表、代码块与表格。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        view = await stream_markdown(pilot)

        assert view.has_class("role-assistant")
        assert view.rendered_text == MARKDOWN_SOURCE
        assert "助手" not in view.rendered_text
        markdown = view.query_one(Markdown)
        assert markdown.source == MARKDOWN_SOURCE
        assert markdown.size.height > 1
        assert markdown.max_scroll_y == 0  # 高度随内容，外层消息流负责滚动（无嵌套滚动）

        assert len(markdown.query("MarkdownH1")) == 1
        assert len(markdown.query("MarkdownBulletList")) == 1
        assert len(markdown.query("MarkdownTable")) == 1
        fence = markdown.query_one("MarkdownFence")
        assert fence.code.strip() == "print(1)"
        assert fence.lexer == "python"


async def test_assistant_markdown_grows_before_message_end() -> None:
    """Markdown 流在 MessageEnd 之前就落屏：增量到达即能看到已解析的结构。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageUpdate("m1", TextDelta("# 进行中")))
        await pilot.pause()
        view = app.query_one(MessageView)
        assert view.rendered_text == "# 进行中"
        assert view.query_one(Markdown).source == "# 进行中"
        assert len(view.query_one(Markdown).query("MarkdownH1")) == 1


async def test_user_and_system_messages_are_plain_colored_text_without_prefix() -> None:
    """user/system 无角色前缀、不被当作 Markdown 解析，分别以 accent 与 warning 呈现。"""
    app, _ = make_app(startup_notices=["启动告警"])
    async with app.run_test() as pilot:
        await submit(pilot, "用 *强调* 不是 Markdown")
        views = list(app.query_one(MessageStream).query(MessageView))
        system_view, user_view = views[0], views[1]

        assert system_view.rendered_text == "启动告警"
        assert user_view.rendered_text == "用 *强调* 不是 Markdown"
        assert not system_view.query(Markdown)
        assert not user_view.query(Markdown)

        assert system_view.has_class("role-system")
        assert user_view.has_class("role-user")
        system_text = system_view.query_one(Static)
        user_text = user_view.query_one(Static)
        assert system_text.has_class("message-text")
        assert user_text.has_class("message-text")
        variables = app.get_css_variables()
        assert system_text.styles.color == Color.parse(variables["warning"])
        assert user_text.styles.color == Color.parse(variables["accent"])


async def test_empty_assistant_has_placeholder_without_role_prefix() -> None:
    """空消息只显示占位，不出现任何角色标签。"""
    app, _ = make_app()
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageEnd("m1"))
        await pilot.pause()
        view = app.query_one(MessageView)
        assert view.rendered_text == "（无内容）"
        assert "助手" not in view.rendered_text

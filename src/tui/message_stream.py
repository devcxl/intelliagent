"""消息流容器：按事件顺序追加消息单元与工具面板，并维持贴底跟随（issue #91）。

Textual 的 anchor 正好表达「新内容到达时贴底，用户移动滚动位置后停止」：程序性
``scroll_end`` 不释放 anchor，用户滚动或 Ctrl+Home 会释放。本模块只在「滚回底部」时
重新 anchor，避免把用户上滚误判为跟随。
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.widget import Widget

from src.tui.message_view import MessageView


class MessageStream(VerticalScroll):
    """消息流区域：追加消息单元和工具调用面板，贴底时跟随新内容。"""

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._following = True
        self._messages: list[MessageView] = []

    @property
    def following(self) -> bool:
        """是否处于贴底跟随状态（用户上滚后为 False，Ctrl+End 或回底恢复）。"""
        return self._following

    def on_mount(self) -> None:
        """初始贴底：之后的增量、工具面板与新消息通过 anchor 自动跟随。"""
        self.anchor()

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        """滚动位置变化时同步跟随状态；滚回底部即恢复跟随（用户滚动与程序性滚动同规则）。"""
        super().watch_scroll_y(old_value, new_value)
        if not self.is_mounted:
            return
        at_bottom = self.is_vertical_scroll_end
        self._following = at_bottom
        if at_bottom:
            self.anchor()

    def add_message(self, view: MessageView) -> None:
        """追加一个消息单元到流末尾（贴底时 anchor 会自动滚到新内容）。"""
        self._messages.append(view)
        self.mount(view)

    def add_tool_panel(self, panel: Widget) -> None:
        """追加一个工具调用折叠面板到流末尾。"""
        self.mount(panel)

    def flush_pending(self) -> None:
        """半程清算：缺 MessageEnd 的消息按收束落屏——缓冲增量落屏，空消息落空态占位。

        已 finish 的单元幂等跳过。
        """
        for view in self._messages:
            view.settle()

    def page_up(self) -> None:
        """PgUp：上翻一页；离开底部后停止跟随。"""
        self.scroll_page_up(animate=False)

    def page_down(self) -> None:
        """PgDn：下翻一页；滚到底部时 watch_scroll_y 恢复跟随。"""
        self.scroll_page_down(animate=False)

    def scroll_top(self) -> None:
        """Ctrl+Home：跳到消息流顶部并停止跟随。"""
        self._following = False
        self.scroll_home(animate=False)

    def follow_latest(self) -> None:
        """Ctrl+End：回到最新输出并恢复跟随。"""
        self._following = True
        self.anchor()

"""多行提示词编辑器：承载 pi 键位与本次会话历史（issue #89）。

TextArea 原生把 Enter 当文本插入，Ctrl+C/Ctrl+D 走复制/删字绑定；本模块在按键进入
原生处理前拦截，把「提交、换行、中止、退出、历史」固化为显式契约。应用层只接收
Submitted 消息，不关心键位细节。
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea

MIN_HEIGHT = 3
"""编辑器至少保留的行数：空闲时也留出编辑空间。"""

MAX_HEIGHT = 8
"""编辑器最多长到 8 行：超出后内部滚动，避免挤占消息流。"""

MAX_HISTORY = 100
"""本次会话保留的提示词历史条数上限。"""

BORDER_TOP_HEIGHT = 1
"""编辑器顶部分隔线的占高：高度按内容行数计算，需额外计入边框。"""

PLACEHOLDER = "输入任务…… Enter 提交，Shift+Enter 或 Ctrl+J 换行"


class PromptEditor(TextArea):
    """多行提示词编辑器：Enter 提交，Shift+Enter/Ctrl+J 换行，高度 3–8 行自适应。"""

    class Submitted(Message):
        """用户要求提交编辑器内容；queue 表示 Alt+Enter 的排队意图。"""

        def __init__(self, text: str, *, queue: bool = False) -> None:
            super().__init__()
            self.text = text
            self.queue = queue

        @property
        def control(self) -> PromptEditor:
            """发送消息的编辑器（Textual 消息惯例）。"""
            return self._sender  # type: ignore[return-value]

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(placeholder=PLACEHOLDER, id=id, classes=classes)
        self._prompt_history: list[str] = []
        self._history_index = 0
        self._sync_height()

    @property
    def prompt_history(self) -> list[str]:
        """本次会话已提交的提示词（旧 → 新），供测试与诊断读取。"""
        return list(self._prompt_history)

    def remember(self, text: str) -> None:
        """记录一条已提交的提示词；超出上限时丢弃最旧的一条。"""
        self._prompt_history.append(text)
        if len(self._prompt_history) > MAX_HISTORY:
            del self._prompt_history[: len(self._prompt_history) - MAX_HISTORY]
        self._history_index = len(self._prompt_history)

    async def _on_key(self, event: events.Key) -> None:
        """在 TextArea 原生按键处理前拦截编辑器契约键位。"""
        key = event.key
        if key in ("shift+enter", "ctrl+j"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        if key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self.text))
            return
        if key == "alt+enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submitted(self.text, queue=True))
            return
        if key == "ctrl+c":
            event.stop()
            event.prevent_default()
            self._ctrl_c()
            return
        if key == "ctrl+d":
            event.stop()
            event.prevent_default()
            self._ctrl_d()
            return
        if key in ("ctrl+p", "ctrl+n"):
            event.stop()
            event.prevent_default()
            self._browse_history(older=key == "ctrl+p")
            return
        await super()._on_key(event)

    def on_text_area_changed(self) -> None:
        """内容变化后按逻辑行数调整高度。"""
        self._sync_height()

    def _sync_height(self) -> None:
        """高度随内容在 MIN_HEIGHT 与 MAX_HEIGHT 之间变化（不含顶部边框）。"""
        lines = self.document.line_count
        rows = max(MIN_HEIGHT, min(MAX_HEIGHT, lines))
        self.styles.height = rows + BORDER_TOP_HEIGHT

    def _ctrl_c(self) -> None:
        """Ctrl+C：有选中文本复制，输入非空清空，输入为空退出。"""
        selected = self.selected_text
        if selected:
            self.app.copy_to_clipboard(selected)
        elif self.text:
            self.clear()
        else:
            self.app.exit()

    def _ctrl_d(self) -> None:
        """Ctrl+D：输入为空退出，非空删除光标右侧字符。"""
        if self.text:
            self.action_delete_right()
        else:
            self.app.exit()

    def _browse_history(self, *, older: bool) -> None:
        """在本次会话历史中后退（Ctrl+P）或前进（Ctrl+N），不占用方向键。"""
        if not self._prompt_history:
            return
        if older:
            if self._history_index == len(self._prompt_history):
                self._history_index = len(self._prompt_history) - 1
            else:
                self._history_index = max(0, self._history_index - 1)
        elif self._history_index >= len(self._prompt_history) - 1:
            self._history_index = len(self._prompt_history)
            self.clear()
            return
        else:
            self._history_index += 1
        self.text = self._prompt_history[self._history_index]
        self.move_cursor(self.document.end)

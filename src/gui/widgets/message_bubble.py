"""消息气泡组件 — 根据事件类型工厂式创建对应 UI。"""

import json

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QTextEdit, QVBoxLayout

from src.gui.styles.markdown import MarkdownRenderer

_markdown_renderer = MarkdownRenderer()


class _UserBubble(QFrame):
    """用户消息 — 右对齐蓝色气泡。"""

    def __init__(self, content: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("userBubble")
        self.setStyleSheet(
            "#userBubble {  background-color: #0078D4;  color: white;  border-radius: 8px;  padding: 8px 12px;}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(content)
        label.setWordWrap(True)
        label.setStyleSheet("color: white;")
        layout.addWidget(label)


class _ThoughtBubble(QLabel):
    """思考过程 — 灰色斜体小字号。"""

    def __init__(self, content: str, parent=None) -> None:
        super().__init__(parent)
        self.setText(content)
        self.setWordWrap(True)
        font = QFont()
        font.setItalic(True)
        font.setPointSize(font.pointSize() - 1)
        self.setFont(font)
        self.setStyleSheet("color: #888; margin: 4px 0;")


class _ToolCallCard(QFrame):
    """工具调用卡片 — 点击可展开/折叠参数详情。"""

    def __init__(self, data: dict, parent=None) -> None:
        super().__init__(parent)
        self._expanded = False
        self.setObjectName("toolCallCard")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "#toolCallCard {"
            "  border: 1px solid #ccc;"
            "  border-radius: 6px;"
            "  background-color: #fafafa;"
            "  padding: 6px;"
            "  margin: 4px 0;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Title line: tool name
        tool_name = data.get("name", data.get("tool", "unknown"))
        self._title = QLabel(f"🔧 {tool_name}")
        self._title.setStyleSheet("font-weight: bold; color: #333;")
        layout.addWidget(self._title)

        # Collapsible detail area
        args = data.get("args", data.get("input", {}))
        args_text = json.dumps(args, indent=2, ensure_ascii=False) if args else "（无参数）"
        self._detail = QTextEdit()
        self._detail.setPlainText(args_text)
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(0)
        self._detail.setStyleSheet("border: none; background: transparent; font-family: monospace; font-size: 12px;")
        layout.addWidget(self._detail)

        self._title.mousePressEvent = lambda _: self._toggle()

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._detail.setMaximumHeight(400 if self._expanded else 0)
        if self._expanded:
            self._detail.setStyleSheet(
                "border: 1px solid #ddd; background: #f0f0f0; font-family: monospace; font-size: 12px; padding: 4px;"
            )
        else:
            self._detail.setStyleSheet(
                "border: none; background: transparent; font-family: monospace; font-size: 12px;"
            )


class _ObservationBlock(QFrame):
    """工具执行结果 — 深色背景等宽字体回显。"""

    def __init__(self, content: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("observationBlock")
        self.setStyleSheet(
            "#observationBlock {  background-color: #1e1e1e;  border-radius: 6px;  padding: 8px;  margin: 4px 0;}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        text_edit = QTextEdit()
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True)
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.Monospace)
        text_edit.setFont(font)
        text_edit.setStyleSheet("color: #d4d4d4; background: transparent; border: none;")
        layout.addWidget(text_edit)


class _AnswerBubble(QFrame):
    """最终回答 — Markdown 渲染。"""

    def __init__(self, content: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("answerBubble")
        self.setStyleSheet("#answerBubble {  border: none;  margin: 4px 0;}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        _markdown_renderer.apply_to_text_edit(text_edit, content)
        layout.addWidget(text_edit)


class MessageBubble(QFrame):
    """Factory-style widget that renders a single message/event.

    Usage::

        bubble = MessageBubble.create("thought", {"content": "..."}, parent)
        layout.addWidget(bubble)
    """

    @staticmethod
    def create(event_type: str, data: dict, parent=None) -> QFrame:
        """Create the appropriate message bubble widget for the event type.

        Args:
            event_type: One of "user", "thought", "action", "observation", "answer".
            data: Event payload dict.
            parent: Optional parent widget.

        Returns:
            A QFrame subclass instance suitable for the event type.
        """
        if event_type == "user":
            return _UserBubble(data.get("content", ""), parent)
        elif event_type == "thought":
            return _ThoughtBubble(data.get("content", ""), parent)
        elif event_type == "action":
            return _ToolCallCard(data, parent)
        elif event_type == "observation":
            return _ObservationBlock(data.get("content", ""), parent)
        elif event_type == "answer":
            return _AnswerBubble(data.get("content", ""), parent)
        else:
            # Fallback: render as plain text
            return _AnswerBubble(data.get("content", str(data)), parent)

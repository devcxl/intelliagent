"""消息气泡组件 — 根据事件类型工厂式创建对应 UI。

所有内部文本组件禁用独立滚动条，由外层 ChatView (QScrollArea) 统一管理滚动。
"""

import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from src.gui.styles.markdown import MarkdownRenderer

_markdown_renderer = MarkdownRenderer()


def _no_scroll_text(parent=None) -> QTextEdit:
    """Create a read-only QTextEdit that never shows its own scrollbar."""
    w = QTextEdit(parent)
    w.setReadOnly(True)
    w.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    # Auto-resize height to fit content
    w.document().documentLayout().documentSizeChanged.connect(lambda: _auto_height(w))
    return w


def _auto_height(text_edit: QTextEdit) -> None:
    """Set QTextEdit's fixed height to exactly fit its document content."""
    doc = text_edit.document()
    doc.setTextWidth(text_edit.viewport().width())
    margins = text_edit.contentsMargins()
    h = int(doc.size().height()) + margins.top() + margins.bottom() + 4
    text_edit.setFixedHeight(h)


# ── Bubble Classes ───────────────────────────────────────────────


class _UserBubble(QFrame):
    def __init__(self, content: str, parent=None):
        super().__init__(parent)
        self.setObjectName("userBubble")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(content)
        label.setWordWrap(True)
        label.setMaximumWidth(500)
        layout.addWidget(label)


class _ThoughtBubble(QLabel):
    def __init__(self, content: str, parent=None):
        super().__init__(parent)
        self.setObjectName("thoughtBubble")
        self.setText(content)
        self.setWordWrap(True)


class _ToolCallCard(QFrame):
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._expanded = False
        self.setObjectName("toolCard")
        self.setFrameShape(QFrame.StyledPanel)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        tool_name = data.get("name", data.get("tool", "unknown"))
        self._title = QLabel(f"🔧 {tool_name}")
        self._title.setObjectName("toolCardTitle")
        self._title.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self._title)

        args = data.get("args", data.get("input", {}))
        args_text = json.dumps(args, indent=2, ensure_ascii=False) if args else "（无参数）"
        self._detail = _no_scroll_text(self)
        self._detail.setObjectName("toolCardArg")
        self._detail.setPlainText(args_text)
        self._detail.setVisible(False)
        layout.addWidget(self._detail)

        # Use QLabel click instead of mousePressEvent override
        self._title.mousePressEvent = lambda _: self._toggle()

    def _toggle(self):
        self._expanded = not self._expanded
        self._detail.setVisible(self._expanded)


class _ObservationBlock(QFrame):
    def __init__(self, content: str, parent=None):
        super().__init__(parent)
        self.setObjectName("observationBlock")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)

        text_edit = _no_scroll_text(self)
        text_edit.setObjectName("observationBlock")
        text_edit.setPlainText(content)
        font = QFont("Courier New", 10)
        font.setStyleHint(QFont.Monospace)
        text_edit.setFont(font)
        layout.addWidget(text_edit)


class _AnswerBubble(QFrame):
    def __init__(self, content: str, parent=None):
        super().__init__(parent)
        self.setObjectName("answerBubble")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        text_edit = _no_scroll_text(self)
        text_edit.setObjectName("answerBubble")
        _markdown_renderer.apply_to_text_edit(text_edit, content)
        layout.addWidget(text_edit)


# ── Factory ──────────────────────────────────────────────────────


class MessageBubble(QFrame):
    @staticmethod
    def create(event_type: str, data: dict, parent=None) -> QFrame:
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
            return _AnswerBubble(data.get("content", str(data)), parent)

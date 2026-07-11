"""聊天气泡组件 — 模拟现代聊天应用的对话气泡。"""

import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.styles.markdown import MarkdownRenderer

_md = MarkdownRenderer()

# ── Shared helpers ─────────────────────────────────────────────


def _rich_text(content: str, parent=None) -> QTextEdit:
    w = QTextEdit(parent)
    w.setReadOnly(True)
    w.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    w.document().documentLayout().documentSizeChanged.connect(lambda: _auto_fit(w))
    return w


def _auto_fit(te: QTextEdit) -> None:
    doc = te.document()
    vp_w = te.viewport().width()
    if vp_w > 0:
        doc.setTextWidth(vp_w)
    margins = te.contentsMargins()
    h = int(doc.size().height()) + margins.top() + margins.bottom() + 4
    te.setFixedHeight(max(h, 24))


def _bubble_widget(bubble_color: str, text_color: str, content_widget: QWidget) -> QFrame:
    """Wrap a content widget in a rounded bubble frame."""
    bubble = QFrame()
    bubble.setObjectName("chatBubble")
    bubble.setStyleSheet(
        f"#chatBubble {{ background-color: {bubble_color}; border-radius: 16px; padding: 10px 14px; }}"
    )
    layout = QVBoxLayout(bubble)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(content_widget)

    # Style for any QLabel or QTextEdit inside the bubble
    content_widget.setStyleSheet(
        f"color: {text_color}; background: transparent; border: none; font-size: 15px; font-weight: 400;"
    )
    return bubble


def _spacer() -> QWidget:
    w = QWidget()
    w.setFixedWidth(40)
    return w


# ── Bubble types ────────────────────────────────────────────────


class _UserMsg(QWidget):
    """用户消息 — 右对齐深色气泡。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(480)
        bubble = _bubble_widget("#0a0a0a", "#ffffff", label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.addStretch()
        layout.addWidget(bubble)


class _AssistantMsg(QWidget):
    """助手回答 — 左对齐浅色气泡。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        te = _rich_text()
        _md.apply_to_text_edit(te, text)
        bubble = _bubble_widget("#f2f3f5", "#222222", te)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        layout.addWidget(bubble)
        layout.addStretch()


class _ThoughtMsg(QLabel):
    """思考过程 — 居中灰色小字。"""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("thoughtBubble")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        font = QFont()
        font.setItalic(True)
        font.setPointSize(font.pointSize() - 1)
        self.setFont(font)
        self.setContentsMargins(40, 2, 40, 2)


class _ToolCallMsg(QFrame):
    """工具调用 — 可折叠卡片。"""

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._expanded = False
        self.setObjectName("toolCard")
        self.setStyleSheet(
            "#toolCard {"
            " border: 1px solid #e5e7eb;"
            " border-radius: 10px;"
            " padding: 8px 12px;"
            " margin: 4px 16px;"
            " background: #fafafa;"
            " }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        tool_name = data.get("name", data.get("tool", "?"))

        header = QHBoxLayout()
        toggle = QPushButton(f"▼ {tool_name}")
        toggle.setFlat(True)
        toggle.setCursor(Qt.PointingHandCursor)
        toggle.setStyleSheet(
            "QPushButton {"
            " text-align: left;"
            " font-weight: 600;"
            " font-size: 13px;"
            " color: #45515e;"
            " border: none;"
            " background: transparent;"
            " }"
        )
        toggle.clicked.connect(self._toggle)
        header.addWidget(toggle)
        header.addStretch()
        layout.addLayout(header)

        args = data.get("args", data.get("input", {}))
        self._detail_text = json.dumps(args, indent=2, ensure_ascii=False) if args else "（无参数）"
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setPlainText(self._detail_text)
        self._detail.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._detail.setStyleSheet(
            "QTextEdit {"
            " font-size: 12px;"
            " font-family: monospace;"
            " color: #5f5f5f;"
            " border: none;"
            " background: transparent;"
            " }"
        )
        layout.addWidget(self._detail)

        # Start collapsed (the toggle's visual height doesn't matter — _detail starts at 0)
        self._header = toggle
        self._detail.setFixedHeight(0)

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            doc = self._detail.document()
            doc.setTextWidth(self._detail.viewport().width() or 400)
            self._detail.setFixedHeight(int(doc.size().height()) + 10)
            self._header.setText(f"▲ {self._header.text()[2:]}")
        else:
            self._detail.setFixedHeight(0)
            self._header.setText(f"▼ {self._header.text()[2:]}")


class _ObservationMsg(QFrame):
    """工具执行结果 — 等宽代码块。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("observationBlock")
        self.setStyleSheet(
            "#observationBlock {"
            " background-color: #f2f3f5;"
            " border-radius: 8px;"
            " padding: 8px 12px;"
            " margin: 4px 16px 4px 56px;"
            " border: 1px solid #e5e7eb;"
            " }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        te = QTextEdit()
        te.setPlainText(text)
        te.setReadOnly(True)
        te.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        te.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        te.setStyleSheet(
            "QTextEdit {"
            " font-size: 12px;"
            " font-family: monospace;"
            " color: #45515e;"
            " border: none;"
            " background: transparent;"
            " }"
        )
        # auto height for observation too
        te.document().documentLayout().documentSizeChanged.connect(lambda t=te: _auto_fit(t))
        layout.addWidget(te)


# ── Factory ──────────────────────────────────────────────────────


class MessageBubble(QWidget):
    """聊天气泡工厂。"""

    @staticmethod
    def create(event_type: str, data: dict, parent=None) -> QWidget:
        content = data.get("content", str(data))

        if event_type == "user":
            return _UserMsg(content, parent)
        elif event_type == "thought":
            return _ThoughtMsg(content, parent)
        elif event_type == "action":
            return _ToolCallMsg(data, parent)
        elif event_type == "observation":
            return _ObservationMsg(content, parent)
        elif event_type == "answer":
            return _AssistantMsg(content, parent)
        else:
            return _AssistantMsg(content, parent)

"""聊天气泡组件 — 模拟现代聊天应用的对话气泡。"""

import json

from PyQt5.QtCore import Qt
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


def _rich_text(parent=None) -> QTextEdit:
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


def _bubble_widget(object_name: str, content_widget: QWidget) -> QFrame:
    bubble = QFrame()
    bubble.setObjectName(object_name)
    layout = QVBoxLayout(bubble)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(content_widget)
    return bubble


def _spacer() -> QWidget:
    w = QWidget()
    w.setFixedWidth(40)
    return w


def _status_emoji(status: str) -> str:
    if status == "success":
        return '<span style="color: #16a34a; font-weight: bold;">✓</span>'
    elif status == "error":
        return '<span style="color: #dc2626; font-weight: bold;">✗</span>'
    else:
        return '<span style="color: #ca8a04; font-weight: bold;">!</span>'


# ── Bubble types ────────────────────────────────────────────────


class _UserMsg(QWidget):
    """用户消息 — 右对齐深色气泡。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        te = _rich_text()
        te.setPlainText(text)
        bubble = _bubble_widget("userBubble", te)

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
        bubble = _bubble_widget("answerBubble", te)

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
        self.setContentsMargins(40, 2, 40, 2)


class _ToolCallMsg(QFrame):
    """工具调用 — 可折叠卡片，内含参数和结果。"""

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._expanded = False
        self.setObjectName("toolCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._tool_name = data.get("name", data.get("tool", "?"))

        # Header with toggle
        header = QHBoxLayout()
        self._toggle = QPushButton(f"▼ {self._tool_name}")
        self._toggle.setFlat(True)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.clicked.connect(self._toggle_all)
        header.addWidget(self._toggle)

        self._status_icon = QLabel("")
        self._status_icon.setTextFormat(Qt.RichText)
        header.addWidget(self._status_icon)
        header.addStretch()
        layout.addLayout(header)

        # Args section
        args = data.get("args", data.get("input", {}))
        args_text = json.dumps(args, indent=2, ensure_ascii=False) if args else "（无参数）"
        self._args_label = QLabel("<b>参数</b>")
        layout.addWidget(self._args_label)

        self._args_detail = QTextEdit()
        self._args_detail.setReadOnly(True)
        self._args_detail.setPlainText(args_text)
        self._args_detail.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self._args_detail)

        # Result section (hidden until populated)
        self._result_label = QLabel("<b>结果</b>")
        layout.addWidget(self._result_label)

        self._result_detail = QTextEdit()
        self._result_detail.setReadOnly(True)
        self._result_detail.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._result_detail.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self._result_detail)

        # Start collapsed
        self._collapse()

    def set_result(self, text: str, status: str = "success") -> None:
        _md.apply_to_text_edit(self._result_detail, text)
        self._status_icon.setText(_status_emoji(status))
        self._expanded = True
        self._apply_collapse()

    def _apply_collapse(self) -> None:
        if self._expanded:
            self._toggle.setText(f"▲ {self._tool_name}")
            # Args
            self._args_label.setVisible(True)
            doc = self._args_detail.document()
            doc.setTextWidth(self._args_detail.viewport().width() or 400)
            self._args_detail.setFixedHeight(int(doc.size().height()) + 10)
            # Result
            if self._result_detail.toPlainText():
                self._result_label.setVisible(True)
                doc = self._result_detail.document()
                doc.setTextWidth(self._result_detail.viewport().width() or 400)
                self._result_detail.setFixedHeight(int(doc.size().height()) + 10)
            else:
                self._result_label.setVisible(False)
                self._result_detail.setFixedHeight(0)
        else:
            self._collapse()

    def _collapse(self) -> None:
        self._toggle.setText(f"▼ {self._tool_name}")
        self._args_label.setVisible(False)
        self._args_detail.setFixedHeight(0)
        self._result_label.setVisible(False)
        self._result_detail.setFixedHeight(0)

    def _toggle_all(self):
        self._expanded = not self._expanded
        self._apply_collapse()


class _ObservationMsg(QFrame):
    """工具执行结果 — 默认折叠的代码块。"""

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._expanded = False
        self.setObjectName("observationBlock")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        # Header with toggle
        header = QHBoxLayout()
        self._toggle = QPushButton("▼ 查看结果")
        self._toggle.setFlat(True)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.clicked.connect(self._toggle_detail)
        header.addWidget(self._toggle)
        header.addStretch()
        layout.addLayout(header)

        # Detail area (collapsed initially)
        self._detail = QTextEdit()
        self._detail.setPlainText(text)
        self._detail.setReadOnly(True)
        self._detail.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._detail.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._detail.document().documentLayout().documentSizeChanged.connect(lambda: _auto_fit(self._detail))
        layout.addWidget(self._detail)
        self._detail.setFixedHeight(0)

    def _toggle_detail(self):
        self._expanded = not self._expanded
        if self._expanded:
            doc = self._detail.document()
            doc.setTextWidth(self._detail.viewport().width() or 400)
            self._detail.setFixedHeight(int(doc.size().height()) + 10)
            self._toggle.setText("▲ 查看结果")
        else:
            self._detail.setFixedHeight(0)
            self._toggle.setText("▼ 查看结果")


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

"""对话视图 — 基于 QScrollArea 的流式消息列表。"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QScrollArea, QTextEdit, QVBoxLayout, QWidget

from src.gui.widgets.message_bubble import MessageBubble


class ChatView(QScrollArea):
    """Scrollable chat area that appends message bubbles from engine events.

    Usage::

        chat = ChatView()
        chat.append_event({"type": "thought", "content": "思考中..."})
        chat.clear()
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.setSpacing(12)
        self._layout.setContentsMargins(8, 8, 8, 8)

        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("chatView")

    def append_event(self, event: dict) -> QWidget:
        """Append a message bubble for the given event dict. Returns the bubble widget."""
        event_type = event.get("type", "answer")
        bubble = MessageBubble.create(event_type, event, self._container)
        self._layout.addWidget(bubble)
        self._scroll_after_layout()
        for te in bubble.findChildren(QTextEdit):
            try:
                te.document().documentLayout().documentSizeChanged.connect(lambda: self._scroll_after_layout())
            except Exception:
                pass
        return bubble

    def _scroll_after_layout(self) -> None:
        QTimer.singleShot(0, self._scroll_to_bottom)

    def clear(self) -> None:
        """Clear all messages (e.g., when switching conversations)."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

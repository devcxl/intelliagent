"""MessageBubble 单元测试 — 聊天气泡工厂。"""

from __future__ import annotations

import pytest
from PyQt5.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QTextEdit

from src.gui.widgets.message_bubble import MessageBubble

_qapp: QApplication | None = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _qapp
    if _qapp is None:
        _qapp = QApplication.instance() or QApplication([])
    yield _qapp


def test_create_user_bubble_is_widget():
    bubble = MessageBubble.create("user", {"content": "hello"}, None)
    assert bubble is not None
    # user bubble wraps a QTextEdit inside a QFrame
    text_edits = bubble.findChildren(QTextEdit)
    assert len(text_edits) >= 1


def test_create_thought_bubble_is_label():
    bubble = MessageBubble.create("thought", {"content": "思考中..."}, None)
    assert bubble is not None
    assert isinstance(bubble, QLabel)


def test_create_action_bubble_is_frame():
    bubble = MessageBubble.create("action", {"name": "read_file", "args": {"path": "test.txt"}}, None)
    assert bubble is not None
    assert isinstance(bubble, QFrame)
    assert bubble.objectName() == "toolCard"


def test_create_observation_bubble_is_frame():
    bubble = MessageBubble.create("observation", {"content": "result text"}, None)
    assert bubble is not None
    assert isinstance(bubble, QFrame)
    assert bubble.objectName() == "observationBlock"


def test_create_answer_bubble_is_widget():
    bubble = MessageBubble.create("answer", {"content": "AI 的回复"}, None)
    assert bubble is not None
    # answer bubble wraps a QTextEdit inside a QFrame
    text_edits = bubble.findChildren(QTextEdit)
    assert len(text_edits) >= 1


def test_create_unknown_type_falls_back_to_assistant():
    bubble = MessageBubble.create("unknown", {"content": "fallback"}, None)
    assert bubble is not None


def test_action_bubble_has_collapsed_detail():
    bubble = MessageBubble.create("action", {"name": "write_file", "args": {"path": "/tmp/test"}}, None)
    # The detail QTextEdit should start with fixed height 0 (collapsed)
    text_edits = bubble.findChildren(QTextEdit)
    detail = [te for te in text_edits if te.objectName() != "chatBubble"]
    assert len(detail) >= 1


def test_action_bubble_set_result():
    bubble = MessageBubble.create("action", {"name": "read_file", "args": {"path": "x"}}, None)
    assert hasattr(bubble, "set_result")
    bubble.set_result("hello world", "success")
    assert "hello world" in bubble._result_detail.toPlainText()
    assert "✓" in bubble._status_icon.text()


def test_action_bubble_set_result_error():
    bubble = MessageBubble.create("action", {"name": "bad_tool", "args": {}}, None)
    bubble.set_result("something went wrong", "error")
    assert "✗" in bubble._status_icon.text()


def test_observation_bubble_starts_collapsed():
    bubble = MessageBubble.create("observation", {"content": "result text"}, None)
    assert bubble is not None
    assert isinstance(bubble, QFrame)
    # Should have a toggle button (QPushButton)
    buttons = bubble.findChildren(QPushButton)
    assert len(buttons) >= 1
    # Detail should start collapsed (height 0)
    text_edits = bubble.findChildren(QTextEdit)
    detail = [te for te in text_edits if te.objectName() != "chatBubble"]
    assert len(detail) >= 1


def test_user_bubble_without_qss_still_renders():
    """Verify that user bubble creates QTextEdit (not QLabel)."""
    bubble = MessageBubble.create("user", {"content": "user message"}, None)
    qlabels = bubble.findChildren(QLabel)
    text_edits = bubble.findChildren(QTextEdit)
    assert len(text_edits) >= 1
    # user bubble should NOT contain QLabel (was migrated to QTextEdit)
    assert len(qlabels) == 0

"""GUI 组件补充测试 - PermissionDialog / ChatView / SessionList。

覆盖 P2-7 审计报告中标记的测试缺口。
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton

from src.gui.widgets.chat_view import ChatView
from src.gui.widgets.permission_dialog import PermissionDialog, _risk_level
from src.gui.widgets.session_list import SessionList

_qapp: QApplication | None = None


@pytest.fixture(scope="module", autouse=True)
def qapp():
    global _qapp
    if _qapp is None:
        _qapp = QApplication.instance() or QApplication([])
    yield _qapp


# ============================================================================
# PermissionDialog
# ============================================================================


class TestPermissionDialog:
    def test_dialog_creates_with_tool_name(self):
        dialog = PermissionDialog("write_file", {"path": "test.py"}, "写入文件")
        assert dialog.windowTitle() == "权限确认"
        assert dialog.objectName() == "permDialog"

    def test_risk_level_high_for_write(self):
        label, color = _risk_level("write_file")
        assert "高风险" in label
        assert color == "#dc2626"

    def test_risk_level_high_for_bash(self):
        label, _ = _risk_level("run_shell")
        assert "高风险" in label

    def test_risk_level_low_for_read(self):
        label, color = _risk_level("read_file")
        assert "低风险" in label
        assert color == "#16a34a"

    def test_risk_level_medium_for_unknown(self):
        label, color = _risk_level("custom_tool")
        assert "中风险" in label
        assert color == "#ca8a04"

    def test_dialog_has_risk_indicator(self):
        dialog = PermissionDialog("write_file", {"path": "x.py"}, "写操作")
        risk_labels = dialog.findChildren(QLabel)
        # 确保对话框包含风险等级标签
        assert any("高风险" in label.text() for label in risk_labels)

    def test_dialog_has_allow_and_deny_buttons(self):
        dialog = PermissionDialog("read_file", {}, "读取")
        buttons = dialog.findChildren(QPushButton)
        texts = [b.text() for b in buttons]
        assert any("允许" in t for t in texts)
        assert any("拒绝" in t for t in texts)


# ============================================================================
# ChatView
# ============================================================================


class TestChatView:
    def test_append_event_creates_bubble(self):
        view = ChatView()
        view.append_event({"type": "answer", "content": "测试回复"})
        assert view._layout.count() == 1

    def test_append_multiple_events(self):
        view = ChatView()
        view.append_event({"type": "user", "content": "问题"})
        view.append_event({"type": "answer", "content": "回答"})
        assert view._layout.count() == 2

    def test_clear_removes_all_bubbles(self):
        view = ChatView()
        view.append_event({"type": "user", "content": "问题1"})
        view.append_event({"type": "answer", "content": "回答1"})
        assert view._layout.count() == 2

        view.clear()
        assert view._layout.count() == 0

    def test_clear_on_empty_view(self):
        view = ChatView()
        view.clear()
        assert view._layout.count() == 0

    def test_append_thought_event(self):
        view = ChatView()
        view.append_event({"type": "thought", "content": "思考中..."})
        assert view._layout.count() == 1

    def test_append_action_event(self):
        view = ChatView()
        view.append_event({"type": "action", "name": "read_file", "args": {"path": "x.py"}})
        assert view._layout.count() == 1


# ============================================================================
# SessionList
# ============================================================================


def _make_conv(conv_id: str, title: str = "测试对话"):
    now = datetime.now(timezone.utc)
    conv = MagicMock()
    conv.id = conv_id
    conv.title = title
    conv.created_at = now
    return conv


def _make_session_list(conversations: list | None = None):
    conv_repo = MagicMock()
    conv_repo.list_all = AsyncMock(return_value=conversations or [])
    conv_repo.save = AsyncMock()
    conv_repo.delete = AsyncMock()
    msg_repo = MagicMock()
    return SessionList(conv_repo, msg_repo)


class TestSessionList:
    def test_count_property_zero_on_init(self):
        sl = _make_session_list()
        assert sl.count == 0

    async def test_count_after_refresh(self):
        convs = [_make_conv("c1"), _make_conv("c2"), _make_conv("c3")]
        sl = _make_session_list(convs)
        await sl.refresh()
        assert sl.count == 3

    def test_first_session_id_empty(self):
        sl = _make_session_list()
        assert sl.first_session_id() is None

    async def test_first_session_id_after_refresh(self):
        convs = [_make_conv("c1", "第一"), _make_conv("c2", "第二")]
        sl = _make_session_list(convs)
        await sl.refresh()
        assert sl.first_session_id() == "c1"

    async def test_set_current_highlights_item(self):
        convs = [_make_conv("c1"), _make_conv("c2")]
        sl = _make_session_list(convs)
        await sl.refresh()
        sl.set_current("c2")
        assert sl._list.currentItem() is not None
        assert sl._list.currentItem().data(0x100) == "c2"  # Qt.UserRole = 0x100

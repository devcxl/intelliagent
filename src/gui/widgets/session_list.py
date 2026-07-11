"""SessionList — 会话列表侧边栏组件。

提供会话的 CRUD 操作，使用 qasync.asyncSlot 桥接 async repo 与 Qt 事件循环。
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from src.db.models import Conversation
from src.db.repositories._utils import new_uuid
from src.db.repositories.conversation import ConversationRepository
from src.db.repositories.message import MessageRepository


def _format_dt(dt: datetime) -> str:
    """Format a datetime for display in the session list."""
    return dt.strftime("%Y-%m-%d %H:%M")


class SessionList(QWidget):
    """会话列表侧边栏。"""

    session_selected = pyqtSignal(str)  # conversation_id
    session_created = pyqtSignal(str)  # conversation_id
    session_deleted = pyqtSignal(str)  # conversation_id

    def __init__(
        self,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._conv_repo = conversation_repo
        self._msg_repo = message_repo
        self._current_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._new_btn = QPushButton("+ 新建会话")
        self._list = QListWidget()

        layout.addWidget(self._new_btn)
        layout.addWidget(self._list)

        self._new_btn.clicked.connect(self._create_session)
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)

    async def refresh(self) -> None:
        """从数据库重载会话列表。"""
        self._list.clear()
        conversations = await self._conv_repo.list_all()
        for conv in conversations:
            title = conv.title or "新对话"
            label = f"{title} — {_format_dt(conv.created_at)}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, conv.id)
            self._list.addItem(item)

        # 恢复当前选中
        if self._current_id:
            self.set_current(self._current_id)

    @asyncSlot()
    async def _create_session(self) -> None:
        """创建新会话并发射 session_created 信号。"""
        conv = Conversation(id=new_uuid())
        await self._conv_repo.save(conv)
        await self.refresh()
        self.session_created.emit(conv.id)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        conv_id: str = item.data(Qt.UserRole)
        self._current_id = conv_id
        self.session_selected.emit(conv_id)

    def _show_context_menu(self, pos) -> None:
        item = self._list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        delete_action = menu.addAction("删除会话")
        action = menu.exec_(self._list.mapToGlobal(pos))
        if action == delete_action:
            asyncio.ensure_future(self._delete_session(item))

    @asyncSlot()
    async def _delete_session(self, item: QListWidgetItem) -> None:
        reply = QMessageBox.question(
            self,
            "确认删除",
            "确定要删除此会话吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        conv_id: str = item.data(Qt.UserRole)
        await self._conv_repo.delete(conv_id)
        self.session_deleted.emit(conv_id)
        await self.refresh()

    def set_current(self, conversation_id: str) -> None:
        """高亮指定会话。"""
        self._current_id = conversation_id
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.UserRole) == conversation_id:
                self._list.setCurrentItem(item)
                break

"""MainWindow — Discord 风格双栏主窗口，组装所有 GUI 组件。

基于 QFluentWidgets FluentWindow 获取 Fluent Design 样式。
"""

from __future__ import annotations

import asyncio
from typing import Any

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QLabel,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot
from qfluentwidgets import FluentWindow

from src.db.repositories.conversation import ConversationRepository
from src.db.repositories.message import MessageRepository
from src.gui.services.command_parser import CommandParser
from src.gui.services.event_bridge import EventBridge
from src.gui.widgets.chat_view import ChatView
from src.gui.widgets.input_bar import InputBar
from src.gui.widgets.session_list import SessionList

_STATUS_READY = "就绪"
_STATUS_RUNNING = "引擎运行中..."


class MainWindow(FluentWindow):
    """Discord 风格双栏主窗口。"""

    def __init__(
        self,
        bridge: EventBridge,
        conv_repo: ConversationRepository,
        msg_repo: MessageRepository,
    ) -> None:
        super().__init__()
        self._bridge = bridge
        self._conv_repo = conv_repo
        self._msg_repo = msg_repo
        self._current_conv_id: str | None = None
        self._switching = False  # 防止并发切换

        self._command_parser = CommandParser()
        self._session_list = SessionList(conv_repo, msg_repo)
        self._chat_view = ChatView()
        self._input_bar = InputBar(self._command_parser)

        self._setup_content()
        self._register_commands()
        self._connect_signals()

        # Hide built-in navigation
        self.navigationInterface.hide()

        # Deferred init: load session list after event loop is running
        QTimer.singleShot(0, self._post_init)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _setup_content(self) -> None:
        self.setWindowTitle("IntelliAgent")
        self.resize(1200, 800)

        self._session_list.setFixedWidth(220)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._chat_view, stretch=1)
        right_layout.addWidget(self._input_bar, stretch=0)

        self._status_label = QLabel(_STATUS_READY)
        self._status_label.setObjectName("statusLabel")
        self._status_label.setFixedHeight(28)
        right_layout.addWidget(self._status_label, stretch=0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._session_list)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 980])

        self.stackedWidget.addWidget(splitter)
        self.stackedWidget.setCurrentWidget(splitter)

    # ------------------------------------------------------------------
    # 命令
    # ------------------------------------------------------------------

    def _register_commands(self) -> None:
        p = self._command_parser
        p.register("/new", self._cmd_new)
        p.register("/delete", self._cmd_delete)
        p.register("/resume", self._cmd_resume)
        p.register("/help", self._cmd_help)

    def _cmd_new(self, _args: str) -> str:
        asyncio.ensure_future(self._session_list._create_session())
        return ""

    def _cmd_delete(self, _args: str) -> str:
        if self._current_conv_id is None:
            return "当前没有选中会话"
        asyncio.ensure_future(self._do_delete_current())
        return ""

    def _cmd_resume(self, args: str) -> str:
        conv_id = args.strip()
        if not conv_id:
            self._chat_view.append_event({"type": "thought", "content": "用法: /resume <会话ID>"})
            return ""
        asyncio.ensure_future(self._switch_to_session(conv_id))
        return ""

    def _cmd_help(self, _args: str) -> str:
        help_text = "可用命令: /new /delete /resume <id> /help"
        self._chat_view.append_event({"type": "thought", "content": help_text})
        return ""

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._bridge.event_received.connect(self._on_event_received)
        self._bridge.engine_started.connect(self._on_engine_started)
        self._bridge.engine_finished.connect(self._on_engine_finished)
        self._bridge.error_occurred.connect(self._on_error)
        self._session_list.session_selected.connect(self._on_session_selected)
        self._session_list.session_created.connect(self._on_session_created)
        self._input_bar.submitted.connect(self._on_user_submitted)

    # ------------------------------------------------------------------
    # EventBridge 信号
    # ------------------------------------------------------------------

    def _on_event_received(self, event: dict) -> None:
        """安全的追加事件（在主线程执行）。"""
        try:
            event_type = event.get("type", "answer")
            content = event.get("data", event.get("content", str(event)))
            payload = {"type": event_type, "content": content}
            self._chat_view.append_event(payload)
        except Exception:
            pass  # 静默忽略渲染错误，不打断引擎流程

    def _on_engine_started(self) -> None:
        self._input_bar.setEnabled(False)
        self._update_status(_STATUS_RUNNING)

    def _on_engine_finished(self, result: dict[str, Any]) -> None:
        self._input_bar.setEnabled(True)
        self._update_status(_STATUS_READY if result.get("success", False) else "引擎执行出错")

    def _on_error(self, message: str) -> None:
        QMessageBox.critical(self, "引擎错误", message)

    # ------------------------------------------------------------------
    # SessionList 信号
    # ------------------------------------------------------------------

    @asyncSlot()
    async def _on_session_selected(self, conv_id: str) -> None:
        await self._switch_to_session(conv_id)

    @asyncSlot()
    async def _on_session_created(self, conv_id: str) -> None:
        await self._switch_to_session(conv_id)

    # ------------------------------------------------------------------
    # InputBar 信号
    # ------------------------------------------------------------------

    @asyncSlot()
    async def _on_user_submitted(self, text: str) -> None:
        if self._current_conv_id is None:
            await self._session_list._create_session()
        await self._bridge.submit_task(text)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _update_status(self, text: str) -> None:
        prefix = f"会话: {self._current_conv_id[:8]}..." if self._current_conv_id else "无会话"
        self._status_label.setText(f"{prefix} | {text}")

    @asyncSlot()
    async def _post_init(self) -> None:
        """启动后异步加载会话列表（不自动选中，等用户点击）。"""
        try:
            await self._session_list.refresh()
        except Exception:
            pass  # DB 错误不崩溃

    @asyncSlot()
    async def _switch_to_session(self, conv_id: str) -> None:
        """切换到指定会话：更新 bridge、清空 UI、加载历史（防并发）。"""
        if conv_id == self._current_conv_id or self._switching:
            return

        self._switching = True
        try:
            await self._bridge.resume_session(conv_id)
            self._current_conv_id = conv_id
            self._session_list.set_current(conv_id)
            self._update_status(_STATUS_READY)

            # 清空对话区（直接重建容器，避免 deleteLater 残留）
            self._chat_view.clear()
            await self._load_history(conv_id)
        except Exception:
            self._update_status("加载会话历史失败")
        finally:
            self._switching = False

    async def _load_history(self, conv_id: str) -> None:
        """从 DB 加载会话历史消息。"""
        try:
            messages = await self._msg_repo.list_by_conversation(conv_id)
        except Exception:
            return
        for msg in messages:
            event_type = _role_to_event_type(msg.role)
            self._chat_view.append_event({"type": event_type, "content": msg.content})

    @asyncSlot()
    async def _do_delete_current(self) -> None:
        if self._current_conv_id is None:
            return
        try:
            await self._conv_repo.delete(self._current_conv_id)
        except Exception:
            return
        await self._session_list.refresh()
        self._chat_view.clear()
        self._current_conv_id = None
        self._update_status(_STATUS_READY)
        if self._session_list._list.count() > 0:
            first_item = self._session_list._list.item(0)
            await self._switch_to_session(first_item.data(Qt.UserRole))


def _role_to_event_type(role: str) -> str:
    mapping = {"user": "user", "assistant": "answer", "tool": "observation"}
    return mapping.get(role, "answer")

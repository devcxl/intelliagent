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
    """Discord 风格双栏主窗口。

    Layout::

        ┌──────────────┬──────────────────────────────────┐
        │  SessionList  │  ChatView (stretch)              │
        │  (固定 220px) │                                  │
        │              │  ───────────────────────────────  │
        │              │  InputBar (底部, 固定高度)         │
        └──────────────┴──────────────────────────────────┘
        [StatusBar: 当前会话ID | 引擎状态]

    Usage::

        bridge = EventBridge(runtime)
        window = MainWindow(bridge, conv_repo, msg_repo)
        window.show()
    """

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

        self._command_parser = CommandParser()
        self._session_list = SessionList(conv_repo, msg_repo)
        self._chat_view = ChatView()
        self._input_bar = InputBar(self._command_parser)

        self._setup_content()
        self._register_commands()
        self._connect_signals()

        # Hide built-in navigation (we use our own SessionList sidebar)
        self.navigationInterface.hide()

        # Async post-init: load sessions from DB after event loop starts
        QTimer.singleShot(0, self._post_init)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _setup_content(self) -> None:
        """Build the Discord-style layout inside FluentWindow's content area."""
        self.setWindowTitle("IntelliAgent")
        self.resize(1200, 800)

        # -- Left: SessionList --
        self._session_list.setFixedWidth(220)

        # -- Right: ChatView + InputBar + StatusBar --
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._chat_view, stretch=1)
        right_layout.addWidget(self._input_bar, stretch=0)

        # -- Status bar (inline instead of QMainWindow.statusBar) --
        self._status_label = QLabel(_STATUS_READY)
        self._status_label.setFixedHeight(28)
        self._status_label.setStyleSheet(
            "padding: 2px 8px; background: palette(window); border-top: 1px solid palette(mid);"
        )
        right_layout.addWidget(self._status_label, stretch=0)

        # -- Splitter --
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._session_list)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 980])

        # Embed in FluentWindow's content area
        self.stackedWidget.addWidget(splitter)
        self.stackedWidget.setCurrentWidget(splitter)

    # ------------------------------------------------------------------
    # CommandParser 命令注册
    # ------------------------------------------------------------------

    def _register_commands(self) -> None:
        p = self._command_parser
        p.register("/new", self._cmd_new)
        p.register("/delete", self._cmd_delete)
        p.register("/resume", self._cmd_resume)
        p.register("/help", self._cmd_help)

    def _cmd_new(self, _args: str) -> str:
        """创建新会话。"""
        asyncio.ensure_future(self._session_list._create_session())
        return ""

    def _cmd_delete(self, _args: str) -> str:
        """删除当前会话。"""
        if self._current_conv_id is None:
            return "当前没有选中会话"
        asyncio.ensure_future(self._do_delete_current())
        return ""

    def _cmd_resume(self, args: str) -> str:
        """切换到指定会话: /resume <conversation_id>"""
        conv_id = args.strip()
        if not conv_id:
            self._chat_view.append_event(
                {
                    "type": "thought",
                    "content": "用法: /resume <会话ID>",
                }
            )
            return ""
        asyncio.ensure_future(self._switch_to_session(conv_id))
        return ""

    def _cmd_help(self, _args: str) -> str:
        self._chat_view.append_event(
            {
                "type": "thought",
                "content": (
                    "可用命令:\n"
                    "  /new         — 新建会话\n"
                    "  /delete      — 删除当前会话\n"
                    "  /resume <id> — 切换到指定会话\n"
                    "  /help        — 显示此帮助"
                ),
            }
        )
        return ""

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        # EventBridge → ChatView / InputBar / StatusBar
        self._bridge.event_received.connect(self._chat_view.append_event)
        self._bridge.engine_started.connect(self._on_engine_started)
        self._bridge.engine_finished.connect(self._on_engine_finished)
        self._bridge.error_occurred.connect(self._on_error)

        # SessionList → MainWindow
        self._session_list.session_selected.connect(self._on_session_selected)
        self._session_list.session_created.connect(self._on_session_created)

        # InputBar → MainWindow
        self._input_bar.submitted.connect(self._on_user_submitted)

    # ------------------------------------------------------------------
    # EventBridge 信号处理
    # ------------------------------------------------------------------

    def _on_engine_started(self) -> None:
        """引擎开始运行: 禁用输入栏, 更新状态。"""
        self._input_bar.setEnabled(False)
        self._update_status(_STATUS_RUNNING)

    def _on_engine_finished(self, result: dict[str, Any]) -> None:
        """引擎结束运行: 恢复输入栏, 更新状态。"""
        self._input_bar.setEnabled(True)
        if result.get("success", False):
            self._update_status(_STATUS_READY)
        else:
            self._update_status("引擎执行出错")

    def _on_error(self, message: str) -> None:
        """引擎出错: 弹窗提示。"""
        QMessageBox.critical(self, "引擎错误", message)

    # ------------------------------------------------------------------
    # SessionList 信号处理
    # ------------------------------------------------------------------

    @asyncSlot()
    async def _on_session_selected(self, conv_id: str) -> None:
        """用户切换会话: 更新 bridge + 加载历史消息。"""
        await self._switch_to_session(conv_id)

    @asyncSlot()
    async def _on_session_created(self, conv_id: str) -> None:
        """新会话创建完成: 切换到新会话。"""
        await self._switch_to_session(conv_id)

    # ------------------------------------------------------------------
    # InputBar 信号处理
    # ------------------------------------------------------------------

    @asyncSlot()
    async def _on_user_submitted(self, text: str) -> None:
        """用户提交输入: 委托给 EventBridge。"""
        # 如果当前没有会话，先创建一个（/ 开头的命令已在 InputBar 中处理）
        if self._current_conv_id is None:
            await self._session_list._create_session()
        await self._bridge.submit_task(text)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _update_status(self, text: str) -> None:
        """更新状态栏文本。"""
        prefix = f"会话: {self._current_conv_id[:8]}..." if self._current_conv_id else "无会话"
        self._status_label.setText(f"{prefix} | {text}")

    @asyncSlot()
    async def _post_init(self) -> None:
        """应用启动后的异步初始化: 加载会话列表, 选中最新会话。"""
        await self._session_list.refresh()

        # 选中列表中的第一个（最新）会话；没有则创建新会话
        count = self._session_list._list.count()
        if count > 0:
            first_item = self._session_list._list.item(0)
            conv_id: str = first_item.data(Qt.UserRole)
            self._session_list.set_current(conv_id)
            await self._switch_to_session(conv_id)
        else:
            await self._session_list._create_session()

    @asyncSlot()
    async def _switch_to_session(self, conv_id: str) -> None:
        """切换到指定会话: 更新 bridge、加载历史、刷新选中状态。"""
        if conv_id == self._current_conv_id:
            return

        await self._bridge.resume_session(conv_id)
        self._current_conv_id = conv_id
        self._session_list.set_current(conv_id)
        self._update_status(_STATUS_READY)

        # 清空并加载历史消息
        self._chat_view.clear()
        await self._load_history(conv_id)

    async def _load_history(self, conv_id: str) -> None:
        """从数据库加载会话历史消息到 ChatView。"""
        messages = await self._msg_repo.list_by_conversation(conv_id)
        for msg in messages:
            event_type = self._role_to_event_type(msg.role)
            self._chat_view.append_event(
                {
                    "type": event_type,
                    "content": msg.content,
                }
            )

    @staticmethod
    def _role_to_event_type(role: str) -> str:
        """将数据库 role 映射为 ChatView 事件类型。

        DB role: user / assistant / tool / system
        Event type: user / answer / observation / (skip)
        """
        mapping = {
            "user": "user",
            "assistant": "answer",
            "tool": "observation",
        }
        return mapping.get(role, "answer")

    @asyncSlot()
    async def _do_delete_current(self) -> None:
        """删除当前会话（从 /delete 命令触发）。"""
        if self._current_conv_id is None:
            return
        await self._conv_repo.delete(self._current_conv_id)
        await self._session_list.refresh()
        self._chat_view.clear()
        self._current_conv_id = None
        self._update_status(_STATUS_READY)

        # 如果还有其他会话，选第一个
        if self._session_list._list.count() > 0:
            first_item = self._session_list._list.item(0)
            conv_id: str = first_item.data(Qt.UserRole)
            await self._switch_to_session(conv_id)

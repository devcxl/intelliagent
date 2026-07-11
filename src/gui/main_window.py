"""MainWindow — Discord 风格双栏主窗口，组装所有 GUI 组件。"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QLabel,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
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


def _async_guard(coro, on_error=None):
    """安全的 async 任务调度 — 异常不传播到事件循环顶层。"""

    async def _runner():
        try:
            await coro
        except Exception:
            traceback.print_exc()
            if on_error:
                on_error()

    asyncio.ensure_future(_runner())


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
        self._switching = False

        self._command_parser = CommandParser()
        self._session_list = SessionList(conv_repo, msg_repo)
        self._chat_view = ChatView()
        self._input_bar = InputBar(self._command_parser)

        self._setup_content()
        self._register_commands()
        self._connect_signals()

        self.navigationInterface.hide()

        # 延迟加载会话列表（不自动切换）
        QTimer.singleShot(100, lambda: _async_guard(self._session_list.refresh()))

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
        _async_guard(self._session_list._create_session())
        return ""

    def _cmd_delete(self, _args: str) -> str:
        if self._current_conv_id is None:
            return "当前没有选中会话"
        _async_guard(self._do_delete_current())
        return ""

    def _cmd_resume(self, args: str) -> str:
        conv_id = args.strip()
        if not conv_id:
            self._chat_view.append_event({"type": "thought", "content": "用法: /resume <会话ID>"})
            return ""
        _async_guard(self._switch_to_session(conv_id))
        return ""

    def _cmd_help(self, _args: str) -> str:
        self._chat_view.append_event({"type": "thought", "content": "可用命令: /new /delete /resume <id> /help"})
        return ""

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._bridge.event_received.connect(self._on_event_safe)
        self._bridge.engine_started.connect(self._on_engine_started)
        self._bridge.engine_finished.connect(self._on_engine_finished)
        self._bridge.error_occurred.connect(self._on_error)

        self._session_list.session_selected.connect(self._on_session_selected)
        self._session_list.session_created.connect(self._on_session_created)

        self._input_bar.submitted.connect(self._on_user_submitted)

    # ------------------------------------------------------------------
    # EventBridge 信号
    # ------------------------------------------------------------------

    def _on_event_safe(self, event: dict) -> None:
        try:
            event_type = event.get("type", "answer")
            data = event.get("data", event)
            content = data.get("content", str(data)) if isinstance(data, dict) else str(data)
            self._chat_view.append_event({"type": event_type, "content": content})
        except Exception:
            pass

    def _on_engine_started(self) -> None:
        self._input_bar.setEnabled(False)
        self._update_status(_STATUS_RUNNING)

    def _on_engine_finished(self, result: dict[str, Any]) -> None:
        self._input_bar.setEnabled(True)
        ok = isinstance(result, dict) and result.get("success", False)
        self._update_status(_STATUS_READY if ok else "引擎执行出错")

    def _on_error(self, message: str) -> None:
        QMessageBox.critical(self, "引擎错误", message)

    # ------------------------------------------------------------------
    # SessionList 信号 → async guarded
    # ------------------------------------------------------------------

    def _on_session_selected(self, conv_id: str) -> None:
        _async_guard(self._switch_to_session(conv_id))

    def _on_session_created(self, conv_id: str) -> None:
        _async_guard(self._switch_to_session(conv_id))

    # ------------------------------------------------------------------
    # InputBar 信号
    # ------------------------------------------------------------------

    def _on_user_submitted(self, text: str) -> None:
        if self._current_conv_id is None:
            _async_guard(self._session_list._create_session())
        _async_guard(self._bridge.submit_task(text))

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _update_status(self, text: str) -> None:
        prefix = f"会话: {self._current_conv_id[:8]}..." if self._current_conv_id else "无会话"
        self._status_label.setText(f"{prefix} | {text}")

    async def _switch_to_session(self, conv_id: str) -> None:
        if conv_id == self._current_conv_id or self._switching:
            return

        self._switching = True
        prev_id = self._current_conv_id
        try:
            self._bridge.resume_session(conv_id)
            # 更新 UI 状态
            prev_id = self._current_conv_id
            self._current_conv_id = conv_id
            self._session_list.set_current(conv_id)
            self._update_status(_STATUS_READY)

            # 安全清空 UI 后再异步加载
            self._chat_view.clear()
            # 用 _current_conv_id 做快照传给延迟回调，防止并发切换
            target_id = conv_id
            QTimer.singleShot(10, lambda tid=target_id: _async_guard(self._load_history_async(tid)))
        except Exception:
            self._current_conv_id = prev_id
            self._update_status("切换失败")
        finally:
            self._switching = False

    async def _load_history_async(self, conv_id: str) -> None:
        # 二次确认：只有在仍选中目标会话时才加载
        if self._current_conv_id != conv_id:
            return
        try:
            messages = await self._msg_repo.list_by_conversation(conv_id)
        except Exception:
            return
        for msg in messages:
            if self._current_conv_id != conv_id:
                return  # 中途切换到其他会话，停止加载
            self._chat_view.append_event({"type": _role_to_event(msg.role), "content": msg.content})

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
            _async_guard(self._switch_to_session(first_item.data(Qt.UserRole)))


def _role_to_event(role: str) -> str:
    return {"user": "user", "assistant": "answer", "tool": "observation"}.get(role, "answer")

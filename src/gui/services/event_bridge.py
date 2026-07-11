"""EventBridge — 将 AgentRuntime 异步事件桥接到 Qt 信号系统。"""

from __future__ import annotations

import asyncio

from PyQt5.QtCore import QObject, pyqtSignal

from src.runtime.agent_runtime import AgentRuntime


class EventBridge(QObject):
    """桥接 AgentRuntime 异步事件流到 Qt 主线程信号。

    每个引擎事件（thought/action/observation/answer）通过 pyqtSignal 发射，
    qasync 确保信号在 Qt 主线程安全处理。

    Usage:
        bridge = EventBridge(runtime)
        bridge.event_received.connect(self.on_event)
        await bridge.submit_task("用户输入")
    """

    event_received = pyqtSignal(dict)  # noqa: N815 — Qt 命名风格
    engine_started = pyqtSignal()  # noqa: N815
    engine_finished = pyqtSignal(dict)  # noqa: N815  # {success: bool, answer: str, ...}
    error_occurred = pyqtSignal(str)  # noqa: N815

    def __init__(self, runtime: AgentRuntime) -> None:
        super().__init__()
        self._runtime = runtime
        self._task: asyncio.Task[None] | None = None
        self._pending_session_id: str | None = None

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    async def submit_task(self, text: str) -> None:
        """提交用户输入，启动引擎异步事件消费。

        每次调用前会取消上一次未完成的任务，避免重叠执行。
        所有事件通过 pyqtSignal 发射到 Qt 主线程。
        """
        # 取消上次未完成的任务
        self._cancel_current_task()

        self._task = asyncio.create_task(self._run_engine(text))
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def resume_session(self, conversation_id: str) -> None:
        """切换到已有会话，下次 submit_task 将使用此会话。

        Args:
            conversation_id: 目标会话ID
        """
        self._pending_session_id = conversation_id

    def cancel(self) -> None:
        """取消当前正在执行的任务。"""
        self._cancel_current_task()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _cancel_current_task(self) -> None:
        """取消当前任务（如果存在且未完成）。"""
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    async def _switch_session_if_needed(self) -> None:
        """切换到待处理的会话（如有）。"""
        if self._pending_session_id is None:
            return
        # 已在目标会话中，跳过
        if self._runtime.conversation_id == self._pending_session_id:
            self._pending_session_id = None
            return
        # 切换到目标会话（重置内部 session 状态）
        self._runtime.switch_session(self._pending_session_id)
        self._pending_session_id = None

    async def _run_engine(self, text: str) -> None:
        """在后台任务中消费 engine 事件流并发射信号。"""
        # 切换会话（如有待处理的切换）
        await self._switch_session_if_needed()

        self.engine_started.emit()

        try:
            async for event in self._runtime.execute(text):
                self.event_received.emit(dict(event))

            self.engine_finished.emit({"success": True})
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            self.engine_finished.emit({"success": False})

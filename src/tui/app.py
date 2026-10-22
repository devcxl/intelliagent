"""IntelliAgentApp：消息流 + 多行编辑器 + 状态栏的 pi 最简 TUI（ADR 0009、issue #61、#89）。

事件驱动（pi-engine-principles §2）：TuiEventSink 把引擎事件翻译进 TuiTarget 落点（本类实现），
message_update 边收边渲染（issue #63，合并重绘见 MessageView），其余组件按事件整步刷新；
用户消息在提交处本地渲染（引擎事件流不含用户输入，pi 同型）。

执行入口是 TaskRunner（引擎结构上满足）：提交触发 run；运行中提交按显式意图转交 steer
（Enter）或 follow_up（Alt+Enter），避免对运行中的引擎重复 run（Engine 拒绝并发 run）。
每次 run 创建一个线程事件作为 abort 信号，Esc 置位后由引擎在 turn 边界检查。
runner 经 RunnerFactory 装配，把 TUI 的事件出口交给引擎——打破"引擎要 sink、应用要引擎"的构造循环。
"""

from __future__ import annotations

import inspect
import sys
import threading
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.worker import Worker

from src.core.agent_events import EventSink, MessageDelta, RunOutcome
from src.core.engine import RunResult
from src.core.tool_pipeline import Observation
from src.llm.stream import Usage
from src.runtime.plugin_assembly import redact_secrets
from src.tui.editor import PromptEditor
from src.tui.event_sink import TuiEventSink
from src.tui.widgets import MessageStream, MessageView, StatusBar, ToolCallPanel

RUN_STATE_LABELS: dict[RunOutcome, str] = {
    "settled": "已完成",
    "terminated": "已终止",
    "error": "出错",
    "aborted": "已中止",
}

ABORTING_LABEL = "中止中"
"""Esc 已置位 abort 信号、等待 turn 边界收束时的状态栏文案。"""


class TaskRunner(Protocol):
    """TUI 的执行入口（引擎结构上满足）：run 跑一个 Run，steer/follow_up 运行中插话。"""

    async def run(self, task: str | None = None, *, abort: threading.Event | None = None) -> RunResult: ...

    def steer(self, message: str) -> None: ...

    def follow_up(self, message: str) -> None: ...


RunnerFactory = Callable[[EventSink], TaskRunner | Awaitable[TaskRunner]]
"""runner 装配器：接收 TUI 的事件出口，产出 runner；MCP 等异步装配可返回 awaitable。"""


class IntelliAgentApp(App[None]):
    """pi 最简形态：消息流 + 多行编辑器 + 状态栏 + 工具调用折叠；仅消费事件流（ADR 0009）。"""

    CSS = """
    MessageStream { height: 1fr; padding: 0 1; }
    #prompt { height: 3; border: none; border-top: solid $accent; padding: 0 1; }
    StatusBar { height: 1; padding: 0 1; background: $surface; }
    .message { margin: 1 0; }
    ToolCallPanel { margin: 0 1; }
    ToolCallPanel .tool-body { height: auto; max-height: 20; overflow-y: auto; }
    ToolCallPanel .tool-body-text { height: auto; }
    """

    BINDINGS = [
        Binding("escape", "abort_run", "中止", show=False),
        Binding("ctrl+o", "toggle_tool_panels", "展开/折叠工具输出", show=False, priority=True),
    ]
    """Esc 中止当前 run；Ctrl+O 整体切换工具输出；其余键位由编辑器与 Textual 默认绑定承载。"""

    ENABLE_COMMAND_PALETTE = False
    """Ctrl+P 让位给提示词历史（pi 最小集不引入命令面板）。"""

    def __init__(
        self,
        *,
        runner_factory: RunnerFactory,
        model: str,
        cwd: Path,
        on_close: Callable[[], Awaitable[None]] | None = None,
        startup_notices: list[str] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        super().__init__()
        self._sink = TuiEventSink(self)
        self._runner_factory = runner_factory
        self._runner: TaskRunner | None = None
        self._pending_runner: Awaitable[TaskRunner] | None = None
        built = runner_factory(self._sink)
        if inspect.isawaitable(built):
            self._pending_runner = built
        else:
            self._runner = built
        self._stream = MessageStream(id="message-stream")
        self._prompt = PromptEditor(id="prompt")
        self._status = StatusBar(cwd, model, clock=clock)
        self._messages: dict[str, MessageView] = {}
        self._tool_panels: dict[str, ToolCallPanel] = {}
        self._run_worker: Worker[None] | None = None
        self._run_settled = False
        self._abort_event: threading.Event | None = None
        self._on_close = on_close
        self._startup_notices = startup_notices if startup_notices is not None else []

    @property
    def event_sink(self) -> TuiEventSink:
        """引擎事件出口：与 runner 的 sink 是同一对象，事件由此进入界面。"""
        return self._sink

    @property
    def task_runner(self) -> TaskRunner | None:
        """执行入口（引擎），供组装诊断与测试读取；异步装配完成前为 None。"""
        return self._runner

    def compose(self) -> ComposeResult:
        yield self._stream
        yield self._prompt
        yield self._status

    async def on_mount(self) -> None:
        """完成可能异步的 runner 装配（MCP connect 等），再开始接收输入。"""
        try:
            if self._pending_runner is not None:
                self._runner = await self._pending_runner
                self._pending_runner = None
        except Exception as exc:
            sys.stderr.write(f"error: {redact_secrets(str(exc))}\n")
            self._status.set_run_state("启动失败")
            self._prompt.disabled = True
            self.exit(return_code=2)
            return
        for notice in self._startup_notices:
            self._stream.add_message(MessageView("system", text=notice))
        self._prompt.focus()

    async def on_unmount(self) -> None:
        """应用退出时释放运行时资源（例如 storage 连接）。"""
        if self._on_close is not None:
            await self._on_close()

    def on_prompt_editor_submitted(self, event: PromptEditor.Submitted) -> None:
        """编辑器提交：Enter 为提交/插话，Alt+Enter 为排队。"""
        self._submit(event.text, queue=event.queue)

    def action_abort_run(self) -> None:
        """Esc：运行中置位 abort 信号并显示「中止中」；空闲或已收束时无副作用。"""
        if self._run_worker is None or self._run_worker.is_finished or self._run_settled:
            return
        if self._abort_event is None or self._abort_event.is_set():
            return
        self._abort_event.set()
        self._status.set_run_state(ABORTING_LABEL)

    def action_toggle_tool_panels(self) -> None:
        """Ctrl+O：整体切换工具输出；存在折叠面板时全部展开，否则全部折叠。"""
        panels = list(self._stream.query(ToolCallPanel))
        if not panels:
            return
        expand = any(panel.collapsed for panel in panels)
        for panel in panels:
            panel.collapsed = not expand

    def _submit(self, text: str, *, queue: bool = False) -> None:
        """提交：清空编辑器、记录历史、本地渲染用户消息，并按运行状态分派。

        运行中 Enter 转交 steer（引擎的插话 seam），Alt+Enter 转交 follow_up；引擎已收束
        （agent_end 已发）而 worker 尚未回收的窗口期统一走 follow_up——steering 队列此时
        已无消费点，直接 steer 会静默丢失。空白提交忽略；非空提交保留原始格式（缩进、
        行尾空格与末尾换行）交给历史、消息视图与 runner。
        """
        if not text.strip() or self._runner is None:
            return
        self._prompt.clear()
        self._prompt.remember(text)
        self._stream.add_message(MessageView("user", text=text))
        if self._run_worker is not None and not self._run_worker.is_finished:
            if queue or self._run_settled:
                self._runner.follow_up(text)
            else:
                self._runner.steer(text)
            return
        self._run_settled = False
        self._abort_event = threading.Event()
        self._run_worker = self.run_worker(self._run(text, self._abort_event), exclusive=True)

    async def _run(self, task: str, abort: threading.Event) -> None:
        """跑一个 Run；异常不逃逸出 worker（引擎已发 agent_end 收束事件），错误落到消息流与状态栏。

        异常收束时缺 MessageEnd 的半程增量在此清算落屏（PR #76 审查遗留）。
        """
        if self._runner is None:
            return
        try:
            await self._runner.run(task, abort=abort)
        except Exception as exc:
            self._stream.flush_pending()
            self._stream.add_message(MessageView("system", text=f"运行异常：{redact_secrets(str(exc))}"))
            self._status.finish_run(RUN_STATE_LABELS["error"])

    # --- TuiTarget 落点（TuiEventSink 按事件顺序调用；增量渲染，issue #63：message_update 边收边渲染） ---

    def show_run_started(self) -> None:
        self._status.start_run()
        if self._abort_event is not None and self._abort_event.is_set():
            self._status.set_run_state(ABORTING_LABEL)

    def show_run_finished(self, outcome: RunOutcome) -> None:
        self._run_settled = True
        self._stream.flush_pending()
        self._status.finish_run(RUN_STATE_LABELS[outcome])

    def show_message_started(self, message_id: str, role: str) -> None:
        view = MessageView(role, message_id=message_id)
        self._messages[message_id] = view
        self._stream.add_message(view)

    def show_message_delta(self, message_id: str, delta: MessageDelta) -> None:
        self._messages[message_id].append_delta(delta)

    def show_message_finished(self, message_id: str, usage: Usage | None = None) -> None:
        self._messages[message_id].finish()
        if usage is not None:
            self._status.record_usage(usage)

    def show_tool_started(self, tool_call_id: str, name: str, arguments: str | Mapping[str, Any]) -> None:
        panel = ToolCallPanel(tool_call_id, name, arguments)
        self._tool_panels[tool_call_id] = panel
        self._stream.add_tool_panel(panel)

    def show_tool_progress(self, tool_call_id: str, delta: str) -> None:
        self._tool_panels[tool_call_id].append_progress(delta)

    def show_tool_finished(self, tool_call_id: str, observation: Observation) -> None:
        self._tool_panels[tool_call_id].finish(observation)

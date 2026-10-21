"""IntelliAgentApp：消息流 + 单行输入框 + 状态栏的 pi 最简 TUI（ADR 0009、issue #61）。

事件驱动（pi-engine-principles §2）：TuiEventSink 把引擎事件翻译进 TuiTarget 落点（本类实现），
message_update 边收边渲染（issue #63，合并重绘见 MessageView），其余组件按事件整步刷新；
用户消息在提交处本地渲染（引擎事件流不含用户输入，pi 同型）。

执行入口是 TaskRunner（引擎结构上满足）：提交触发 run；运行中提交转交 steer（引擎的插话 seam），
避免对运行中的引擎重复 run（Engine 拒绝并发 run）。runner 经 RunnerFactory 装配，
把 TUI 的事件出口交给引擎——打破"引擎要 sink、应用要引擎"的构造循环。
"""

from __future__ import annotations

import threading
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from textual.app import App, ComposeResult
from textual.widgets import Input
from textual.worker import Worker

from src.core.agent_events import EventSink, MessageDelta, RunOutcome
from src.core.engine import RunResult
from src.core.tool_pipeline import Observation
from src.runtime.plugin_assembly import redact_secrets
from src.tui.event_sink import TuiEventSink
from src.tui.widgets import MessageStream, MessageView, StatusBar, ToolCallPanel

RUN_STATE_LABELS: dict[RunOutcome, str] = {
    "settled": "已完成",
    "terminated": "已终止",
    "error": "出错",
    "aborted": "已中止",
}


class TaskRunner(Protocol):
    """TUI 的执行入口（引擎结构上满足）：run 跑一个 Run，steer/follow_up 运行中插话。"""

    async def run(self, task: str | None = None, *, abort: threading.Event | None = None) -> RunResult: ...

    def steer(self, message: str) -> None: ...

    def follow_up(self, message: str) -> None: ...


RunnerFactory = Callable[[EventSink], TaskRunner]
"""runner 装配器：接收 TUI 的事件出口，产出绑定该出口的 runner。"""


class IntelliAgentApp(App[None]):
    """pi 最简形态：消息流 + 单行输入 + 状态栏 + 工具调用折叠；仅消费事件流（ADR 0009）。"""

    CSS = """
    MessageStream { height: 1fr; padding: 0 1; }
    #prompt { height: 3; border-top: solid $accent; }
    StatusBar { height: 1; padding: 0 1; background: $surface; }
    .message { margin: 1 0; }
    ToolCallPanel { margin: 0 1; }
    """

    BINDINGS = []

    def __init__(
        self,
        *,
        runner_factory: RunnerFactory,
        model: str,
        cwd: Path,
        on_close: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self._sink = TuiEventSink(self)
        self._runner = runner_factory(self._sink)
        self._stream = MessageStream(id="message-stream")
        self._prompt = Input(id="prompt", placeholder="输入任务…… Enter 提交")
        self._status = StatusBar(cwd, model)
        self._messages: dict[str, MessageView] = {}
        self._tool_panels: dict[str, ToolCallPanel] = {}
        self._run_worker: Worker[None] | None = None
        self._run_settled = False
        self._on_close = on_close

    @property
    def event_sink(self) -> TuiEventSink:
        """引擎事件出口：与 runner 的 sink 是同一对象，事件由此进入界面。"""
        return self._sink

    @property
    def task_runner(self) -> TaskRunner:
        """执行入口（引擎），供组装诊断与测试读取。"""
        return self._runner

    def compose(self) -> ComposeResult:
        yield self._stream
        yield self._prompt
        yield self._status

    def on_mount(self) -> None:
        self._prompt.focus()

    async def on_unmount(self) -> None:
        """应用退出时释放运行时资源（例如 storage 连接）。"""
        if self._on_close is not None:
            await self._on_close()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        """Enter 提交：Input 原生 Submitted 消息触发原有提交动作。"""
        self.action_submit_prompt()

    def action_submit_prompt(self) -> None:
        """提交：清空编辑器、本地渲染用户消息，触发 run。

        运行中提交转交 steer（引擎的插话 seam）；引擎已收束（agent_end 已发）而 worker
        尚未回收的窗口期转 follow_up——steering 队列此时已无消费点，直接 steer 会静默丢失。
        """
        text = self._prompt.value.strip()
        if not text:
            return
        self._prompt.value = ""
        self._stream.add_message(MessageView("user", text=text))
        if self._run_worker is not None and not self._run_worker.is_finished:
            if self._run_settled:
                self._runner.follow_up(text)
            else:
                self._runner.steer(text)
            return
        self._run_settled = False
        self._run_worker = self.run_worker(self._run(text), exclusive=True)

    async def _run(self, task: str) -> None:
        """跑一个 Run；异常不逃逸出 worker（引擎已发 agent_end 收束事件），错误落到消息流与状态栏。

        异常收束时缺 MessageEnd 的半程增量在此清算落屏（PR #76 审查遗留）。
        """
        try:
            await self._runner.run(task)
        except Exception as exc:
            self._stream.flush_pending()
            self._stream.add_message(MessageView("system", text=f"运行异常：{redact_secrets(str(exc))}"))
            self._status.set_run_state(RUN_STATE_LABELS["error"])

    # --- TuiTarget 落点（TuiEventSink 按事件顺序调用；增量渲染，issue #63：message_update 边收边渲染） ---

    def show_run_started(self) -> None:
        self._status.set_run_state("运行中")

    def show_run_finished(self, outcome: RunOutcome) -> None:
        self._run_settled = True
        self._stream.flush_pending()
        self._status.set_run_state(RUN_STATE_LABELS[outcome])

    def show_message_started(self, message_id: str, role: str) -> None:
        view = MessageView(role, message_id=message_id)
        self._messages[message_id] = view
        self._stream.add_message(view)

    def show_message_delta(self, message_id: str, delta: MessageDelta) -> None:
        self._messages[message_id].append_delta(delta)

    def show_message_finished(self, message_id: str) -> None:
        self._messages[message_id].finish()

    def show_tool_started(self, tool_call_id: str, name: str, arguments: str | Mapping[str, Any]) -> None:
        panel = ToolCallPanel(tool_call_id, name, arguments)
        self._tool_panels[tool_call_id] = panel
        self._stream.add_tool_panel(panel)

    def show_tool_progress(self, tool_call_id: str, delta: str) -> None:
        self._tool_panels[tool_call_id].append_progress(delta)

    def show_tool_finished(self, tool_call_id: str, observation: Observation) -> None:
        self._tool_panels[tool_call_id].finish(observation)

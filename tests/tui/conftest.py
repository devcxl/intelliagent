"""TUI 测试的 fake 与装配辅助：脚本化 TaskRunner、pilot 提交助手。

TUI 测试走声明的 seam：提交经多行编辑器（pilot），状态经引擎事件流（EventSink）进入，
不碰持久化、不直接调用组件内部的事件翻译。
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from textual.pilot import Pilot
from textual.widgets import TextArea

from src.core.agent_events import AgentEvent, EventSink
from src.core.engine import RunResult
from src.tui.app import IntelliAgentApp, TaskRunner

DEFAULT_CWD = Path("/work/project")


class ScriptedRunner:
    """脚本化 TaskRunner：按脚本向 sink 发事件，记录提交与插话（不依赖真实引擎）。

    gate 置位后 run() 挂起，供"运行中提交即插话"这类现场断言使用。
    """

    def __init__(self, sink: EventSink) -> None:
        self.sink = sink
        self.tasks: list[str | None] = []
        self.steered: list[str] = []
        self.follow_ups: list[str] = []
        self.gate: asyncio.Event | None = None
        self._scripts: list[list[AgentEvent]] = []

    def enqueue(self, *events: AgentEvent) -> None:
        """排入一次 run 要发出的事件脚本。"""
        self._scripts.append(list(events))

    def steer(self, message: str) -> None:
        self.steered.append(message)

    def follow_up(self, message: str) -> None:
        self.follow_ups.append(message)

    async def run(self, task: str | None = None, *, abort: threading.Event | None = None) -> RunResult:
        self.tasks.append(task)
        for event in self._scripts.pop(0) if self._scripts else []:
            self.sink.emit(event)
        if self.gate is not None:
            await self.gate.wait()
        return RunResult(outcome="settled", turns=1, stop_reason="stop")


class ScriptedRunnerFactory:
    """产出 ScriptedRunner 的 runner_factory；记下产出的 runner 供测试驱动。"""

    def __init__(self) -> None:
        self.runner: ScriptedRunner | None = None

    def __call__(self, sink: EventSink) -> TaskRunner:
        self.runner = ScriptedRunner(sink)
        return self.runner


def make_app(*, model: str = "fake/model", cwd: Path | None = None) -> tuple[IntelliAgentApp, ScriptedRunner]:
    """装配一个带脚本 runner 的 TUI 应用。"""
    factory = ScriptedRunnerFactory()
    app = IntelliAgentApp(runner_factory=factory, model=model, cwd=cwd or DEFAULT_CWD)
    assert factory.runner is not None
    return app, factory.runner


async def submit(pilot: Pilot, text: str) -> None:
    """把文本载入多行编辑器并提交，等待 run worker 收束。

    内容经 load_text 载入：pilot 的键入合成只覆盖可打印 ASCII，文本内容与提交路径分开测。
    """
    prompt = pilot.app.query_one("#prompt", TextArea)
    prompt.focus()
    prompt.load_text(text)
    await pilot.press("ctrl+j")
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()

"""TUI 测试的 fake 与装配辅助：脚本化 TaskRunner、pilot 提交助手。

TUI 测试走声明的 seam：提交经多行编辑器（pilot 按键），状态经引擎事件流（EventSink）进入，
不碰持久化、不直接调用组件内部的事件翻译。
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest
from textual.pilot import Pilot

from src.core.agent_events import AgentEnd, AgentEvent, EventSink
from src.core.engine import RunResult
from src.tui.app import IntelliAgentApp, TaskRunner
from src.tui.editor import PromptEditor

DEFAULT_CWD = Path("/work/project")


@pytest.fixture(autouse=True)
def isolate_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把 HOME 指向测试临时目录，避免开发者本机 skill 影响请求内容。"""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


class ScriptedRunner:
    """脚本化 TaskRunner：按脚本向 sink 发事件，记录提交、插话与中止信号（不依赖真实引擎）。

    gate 置位后 run() 挂起，供"运行中提交即插话"这类现场断言使用；abort 信号置位时
    在收束处模拟引擎的 turn 边界检查，发出 aborted 的 AgentEnd。
    """

    def __init__(self, sink: EventSink) -> None:
        self.sink = sink
        self.tasks: list[str | None] = []
        self.steered: list[str] = []
        self.follow_ups: list[str] = []
        self.abort_events: list[threading.Event] = []
        self.gate: asyncio.Event | None = None
        self.raise_error: Exception | None = None
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
        if abort is not None:
            self.abort_events.append(abort)
        for event in self._scripts.pop(0) if self._scripts else []:
            self.sink.emit(event)
        if self.raise_error is not None:
            raise self.raise_error
        if self.gate is not None:
            await self.gate.wait()
        if abort is not None and abort.is_set():
            self.sink.emit(AgentEnd(outcome="aborted"))
            return RunResult(outcome="aborted", turns=1, stop_reason="aborted")
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
    """把文本写入编辑器并提交，等待 run worker 收束。

    内容直接写入 PromptEditor.text：pilot 的键入合成只覆盖可打印 ASCII，文本内容与提交路径分开测。
    """
    prompt = pilot.app.query_one("#prompt", PromptEditor)
    prompt.focus()
    prompt.text = text
    await pilot.press("enter")
    await pilot.app.workers.wait_for_complete()
    await pilot.pause()

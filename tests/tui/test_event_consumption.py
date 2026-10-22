"""结构性测试：TUI 只消费引擎事件流，不直连持久化（issue #61 验收）。"""

from __future__ import annotations

import ast
import threading
from pathlib import Path

from src.core.agent_events import MessageEnd, MessageStart, MessageUpdate, ToolExecutionEnd, ToolExecutionStart
from src.core.engine import RunResult
from src.core.tool_pipeline import Observation
from src.llm.stream import TextDelta
from src.tui.app import IntelliAgentApp
from src.tui.message_stream import MessageStream
from src.tui.message_view import MessageView
from src.tui.status_bar import StatusBar
from src.tui.tool_panel import ToolCallPanel

REPO_ROOT = Path(__file__).resolve().parents[2]
TUI_ROOT = REPO_ROOT / "src" / "tui"
FORBIDDEN_MODULES = ("src.db", "src.plugins.storage", "src.services", "src.gui", "sqlalchemy", "aiosqlite")


def _imported_modules(path: Path) -> set[str]:
    """收集文件引用的模块全名：含 from X import Y 形成的 X.Y、from . import 展开、from src import db 形态。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
                modules.update(f"{node.module}.{alias.name}" for alias in node.names)
            else:
                modules.update(alias.name for alias in node.names)
    return modules


def test_tui_does_not_touch_persistence() -> None:
    """src/tui 的任何模块都不得引入持久化/旧前端模块——TUI 只消费引擎事件流。

    递归扫描全部子包；静态 import 语法是约定的硬底线（动态 importlib 属 code review
    把关范围，此测试保证无意的直接引用立即变红）。
    """
    assert TUI_ROOT.is_dir()
    for path in sorted(TUI_ROOT.rglob("*.py")):
        for module in _imported_modules(path):
            for forbidden in FORBIDDEN_MODULES:
                assert not (module == forbidden or module.startswith(forbidden + ".")), (
                    f"{path.name} 引入了持久化模块 {module}：TUI 只能消费引擎事件流"
                )


class ExplodingRunner:
    """run/steer 一旦被调用即失败：证明渲染完全由事件驱动，无需执行入口。"""

    async def run(self, task: str | None = None, *, abort: threading.Event | None = None) -> RunResult:
        raise AssertionError("纯渲染不应触发 runner.run")

    def steer(self, message: str) -> None:
        raise AssertionError("纯渲染不应触发 runner.steer")


async def test_rendering_is_driven_by_events_only() -> None:
    app = IntelliAgentApp(runner_factory=lambda sink: ExplodingRunner(), model="fake/model", cwd=Path("/work"))
    async with app.run_test() as pilot:
        sink = app.event_sink
        sink.emit(MessageStart("m1", role="assistant"))
        sink.emit(MessageUpdate("m1", TextDelta("来自事件")))
        sink.emit(MessageEnd("m1"))
        sink.emit(ToolExecutionStart("call_1", "read", {"path": "a.txt"}))
        sink.emit(
            ToolExecutionEnd(
                "call_1",
                Observation(
                    tool_call_id="call_1", name="read", arguments={"path": "a.txt"}, content="ok", status="success"
                ),
            )
        )
        await pilot.pause()
        stream = app.query_one(MessageStream)
        assert [view.text for view in stream.query(MessageView)] == ["来自事件"]
        assert "成功" in app.query_one(ToolCallPanel).title
        assert "就绪" in app.query_one(StatusBar).text

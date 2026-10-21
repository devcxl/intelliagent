"""引擎事件流 seam 测试（Spec #49 seam 1）：fake LLM + 真实 basic_tools + 临时工作区跑完整任务。

只断言事件流、返回值与工作区效果：事件序列逐项核对（含 tool_execution_start 执行前、message_update 增量），
不碰引擎私有属性。
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.agent_events import (
    AgentEnd,
    AgentStart,
    MessageEnd,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
)
from src.core.engine import Engine
from src.core.plugin_host import PluginHost
from src.llm.stream import TextDelta, ToolCallDelta
from src.plugins.basic_tools import BasicToolsPlugin
from src.utils.path_policy import PathPolicy
from tests.core.engine_support import (
    FakeLLM,
    RecordingSink,
    build_engine,
    event_names,
    make_tool,
    text_events,
    tool_call_events,
)

EXPECTED_SEQUENCE = [
    "AgentStart",
    "TurnStart",
    "MessageStart",
    "MessageUpdate",
    "MessageUpdate",
    "MessageEnd",
    "ToolExecutionStart",
    "ToolExecutionEnd",
    "TurnEnd",
    "TurnStart",
    "MessageStart",
    "MessageUpdate",
    "MessageEnd",
    "TurnEnd",
    "AgentEnd",
]


class TestEventStreamSeam:
    """事件流是协议：一次完整任务的事件序列、增量内容与真实状态都可逐项核对。"""

    async def test_full_task_with_real_tools_emits_complete_event_sequence(self, tmp_path: Path) -> None:
        """完整任务：write 落盘 → 文本收尾。事件序列与工具效果都断言。"""
        target = tmp_path / "note.txt"
        host = PluginHost()
        host.load(BasicToolsPlugin(path_policy=PathPolicy(workspace=tmp_path)))
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "write", json.dumps({"path": str(target), "content": "hello"}))]))
        llm.enqueue(*text_events("wrote it"))
        sink = RecordingSink()
        engine = Engine.from_host(host, llm=llm, model="fake/model", sink=sink)

        result = await engine.run("写一个 note.txt")

        assert result.outcome == "settled"
        assert result.turns == 2
        assert target.read_text(encoding="utf-8") == "hello"
        assert event_names(sink.events) == EXPECTED_SEQUENCE

    async def test_event_payloads_carry_streaming_deltas_and_true_status(self, tmp_path: Path) -> None:
        """message_update 携带流式增量；tool_execution_end 的 Observation 状态是真实状态。"""
        target = tmp_path / "note.txt"
        host = PluginHost()
        host.load(BasicToolsPlugin(path_policy=PathPolicy(workspace=tmp_path)))
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "write", json.dumps({"path": str(target), "content": "hello"}))]))
        llm.enqueue(*text_events("wrote", " it"))
        sink = RecordingSink()
        engine = Engine.from_host(host, llm=llm, model="fake/model", sink=sink)

        await engine.run("task")

        updates = [event.delta for event in sink.events if isinstance(event, MessageUpdate)]
        assert isinstance(updates[0], ToolCallDelta)
        assert updates[0].name == "write"
        assert isinstance(updates[2], TextDelta)
        assert updates[2].text == "wrote"
        assert updates[3].text == " it"
        ends = [event for event in sink.events if isinstance(event, MessageEnd)]
        assert [end.stop_reason for end in ends] == ["stop", "stop"]
        observations = [event.observation for event in sink.events if isinstance(event, ToolExecutionEnd)]
        assert [observation.status for observation in observations] == ["success"]
        assert observations[0].tool_call_id == "c1"

    async def test_tool_execution_start_is_emitted_before_side_effects(self, tmp_path: Path) -> None:
        """tool_execution_start 在副作用前发出——"执行中"状态与 permission 拦截的基础。"""
        target = tmp_path / "note.txt"
        host = PluginHost()
        host.load(BasicToolsPlugin(path_policy=PathPolicy(workspace=tmp_path)))
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "write", json.dumps({"path": str(target), "content": "hello"}))]))
        llm.enqueue(*text_events("done"))
        seen: list[bool] = []

        def on_emit(event: object) -> None:
            if isinstance(event, ToolExecutionStart):
                seen.append(target.exists())

        sink = RecordingSink(on_emit=on_emit)
        engine = Engine.from_host(host, llm=llm, model="fake/model", sink=sink)

        await engine.run("task")

        assert seen == [False]
        assert target.read_text(encoding="utf-8") == "hello"

    async def test_failing_tool_reports_error_status_in_event_stream(self) -> None:
        """工具返回错误信封：事件流里的观察状态是 error，不再是硬编码 success。"""
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", '{"path": "a.txt"}')]))
        llm.enqueue(*text_events("done"))
        sink = RecordingSink()
        engine = build_engine(
            llm, tools=[make_tool([], name="rec", result='{"status": "error", "error": "boom"}')], sink=sink
        )

        await engine.run("task")

        observations = [event.observation for event in sink.events if isinstance(event, ToolExecutionEnd)]
        assert [observation.status for observation in observations] == ["error"]
        assert observations[0].error == "boom"


class TestAgentBoundaries:
    """agent_start / agent_end 与 turn_start / turn_end 划分 run 与 turn 边界。"""

    async def test_run_is_bracketed_by_agent_events_and_hard_exit_is_marked(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("answer", stop="error"))
        sink = RecordingSink()
        engine = build_engine(llm, sink=sink)

        result = await engine.run("task")

        assert result.outcome == "error"
        assert isinstance(sink.events[0], AgentStart)
        assert isinstance(sink.events[-1], AgentEnd)
        assert sink.events[-1].outcome == "error"

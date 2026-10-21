"""引擎循环状态机测试：双层循环、stopReason 三分类、历史一致性、terminate 信号与显式 continuation。

规格来源：docs/pi-engine-principles.md §1（runLoop 状态机）、ADR 0010、issue #57。
"""

from __future__ import annotations

import threading

import pytest

from src.core.agent_events import AgentEnd, ToolExecutionEnd
from src.core.tool_pipeline import AfterToolCallHook, Observation, ToolCall
from src.core.turn_hooks import FinishDecision, FinishTurnHook, TurnResult
from src.llm.stream import Done, Error, ToolCallDelta
from src.plugins.basic_tools import tool_error, tool_success
from tests.core.engine_support import (
    FakeLLM,
    RecordingSink,
    assert_tool_calls_paired,
    build_engine,
    make_tool,
    text_events,
    tool_arguments,
    tool_call_events,
)


class TestDoubleLoop:
    """内层循环跑一个 assistant 响应 + 其工具结果；没有工具调用才收束。"""

    async def test_tool_calls_chain_across_turns_until_settle(self) -> None:
        log: list[str] = []
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        llm.enqueue(*tool_call_events([("c2", "rec", tool_arguments("b.txt"))]))
        llm.enqueue(*text_events("done"))
        engine = build_engine(llm, tools=[make_tool(log)])

        result = await engine.run("task")

        assert result.outcome == "settled"
        assert result.turns == 3
        assert result.stop_reason == "stop"
        assert log == ["execute:rec", "execute:rec"]
        assert len(llm.requests) == 3
        assert engine.messages[-1] == {"role": "assistant", "content": "done"}
        assert_tool_calls_paired(engine.messages)

    async def test_second_request_carries_tool_results(self) -> None:
        """工具结果回填后模型下一次请求能看到完整 tool 结果。"""
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        llm.enqueue(*text_events("done"))
        engine = build_engine(llm, tools=[make_tool([])])

        await engine.run("task")

        second = llm.requests[1].messages
        assert [message["role"] for message in second] == ["user", "assistant", "tool"]
        assert second[-1]["tool_call_id"] == "c1"


class TestStopReasonClassification:
    """stopReason 三分类：error/aborted 硬退出且不执行工具；length 全部判失败让模型重发。"""

    async def test_error_stops_run_without_executing_tools(self) -> None:
        log: list[str] = []
        llm = FakeLLM()
        llm.enqueue(
            ToolCallDelta(index=0, id="c1", name="rec", arguments_delta=tool_arguments("a.txt")),
            Error(message="provider exploded"),
            Done(stop_reason="error", usage=None),
        )
        engine = build_engine(llm, tools=[make_tool(log)])

        result = await engine.run("task")

        assert result.outcome == "error"
        assert log == []
        assert len(llm.requests) == 1
        assert_tool_calls_paired(engine.messages)

    async def test_aborted_stops_run_without_executing_tools(self) -> None:
        log: list[str] = []
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))], stop="aborted"))
        engine = build_engine(llm, tools=[make_tool(log)])

        result = await engine.run("task")

        assert result.outcome == "aborted"
        assert log == []
        assert_tool_calls_paired(engine.messages)

    async def test_length_fails_tool_calls_and_asks_model_to_resend(self) -> None:
        log: list[str] = []
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", '{"path": "a.tx')], stop="length"))
        llm.enqueue(*text_events("resent as text"))
        engine = build_engine(llm, tools=[make_tool(log)])

        result = await engine.run("task")

        assert result.outcome == "settled"
        assert result.turns == 2
        assert log == []
        tool_message = llm.requests[1].messages[-1]
        assert tool_message["role"] == "tool"
        assert "truncated" in tool_message["content"]
        assert "complete arguments" in tool_message["content"]
        assert_tool_calls_paired(engine.messages)

    async def test_length_without_tool_calls_settles(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("partial answer", stop="length"))
        engine = build_engine(llm)

        result = await engine.run("task")

        assert result.outcome == "settled"
        assert result.turns == 1
        assert result.stop_reason == "length"


class TestHistoryConsistency:
    """异常路径不留未配对的 assistant tool_calls（旧引擎 P0 缺陷回归）。"""

    async def test_hook_exception_leaves_no_unpaired_tool_calls(self) -> None:
        async def boom(result: TurnResult) -> FinishDecision:
            raise RuntimeError("hook broke")

        log: list[str] = []
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        engine = build_engine(llm, tools=[make_tool(log)], turn_hooks=[FinishTurnHook(callback=boom)])

        with pytest.raises(RuntimeError, match="hook broke"):
            await engine.run("task")

        assert_tool_calls_paired(engine.messages)

    async def test_hard_exit_commits_error_message_paired_with_not_executed_results(self) -> None:
        """error/aborted 硬退出：tool_calls 用"未执行"错误结果配对提交，且工具绝不运行。"""
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))], stop="aborted"))
        engine = build_engine(llm, tools=[make_tool([])])

        await engine.run("task")

        tail = engine.messages[-2:]
        assert tail[0]["role"] == "assistant"
        assert tail[0]["tool_calls"][0]["id"] == "c1"
        assert tail[1]["role"] == "tool"
        assert "not executed" in tail[1]["content"]
        assert_tool_calls_paired(engine.messages)


class TestTerminateSignal:
    """工具批次终止：全部 terminate 才停循环（pi 语义）。"""

    async def test_all_terminate_stops_the_loop(self) -> None:
        llm = FakeLLM()
        llm.enqueue(
            *tool_call_events([("c1", "term", tool_arguments("a.txt")), ("c2", "term", tool_arguments("b.txt"))])
        )
        engine = build_engine(
            llm,
            tools=[make_tool([], name="term", result=tool_success(terminate=True))],
        )

        result = await engine.run("task")

        assert result.outcome == "terminated"
        assert result.turns == 1
        assert len(llm.requests) == 1
        assert_tool_calls_paired(engine.messages)

    async def test_mixed_terminate_batch_continues_the_loop(self) -> None:
        llm = FakeLLM()
        llm.enqueue(
            *tool_call_events([("c1", "term", tool_arguments("a.txt")), ("c2", "rec", tool_arguments("b.txt"))])
        )
        llm.enqueue(*text_events("done"))
        engine = build_engine(
            llm,
            tools=[
                make_tool([], name="term", result=tool_success(terminate=True)),
                make_tool([], name="rec"),
            ],
        )

        result = await engine.run("task")

        assert result.outcome == "settled"
        assert result.turns == 2

    async def test_after_hook_can_request_termination(self) -> None:
        async def terminate(call: ToolCall, observation: Observation) -> Observation:
            return Observation(
                tool_call_id=observation.tool_call_id,
                name=observation.name,
                arguments=observation.arguments,
                content=observation.content,
                status=observation.status,
                terminate=True,
            )

        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        engine = build_engine(llm, tools=[make_tool([])], tool_hooks=[AfterToolCallHook(callback=terminate)])

        result = await engine.run("task")

        assert result.outcome == "terminated"
        assert result.turns == 1


class TestExplicitContinuation:
    """显式 continuation：不加新消息、从现有上下文续跑（pi agentLoopContinue）。"""

    async def test_continuation_resumes_from_tool_result_ending(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "term", tool_arguments("a.txt"))]))
        llm.enqueue(*text_events("continuing"))
        engine = build_engine(llm, tools=[make_tool([], name="term", result=tool_success(terminate=True))])

        first = await engine.run("task")
        second = await engine.run(None)

        assert first.outcome == "terminated"
        assert second.outcome == "settled"
        assert second.turns == 1
        user_messages = [message for message in engine.messages if message["role"] == "user"]
        assert len(user_messages) == 1  # continuation 不加新消息
        assert llm.requests[1].messages == list(engine.messages)[:-1]

    async def test_continuation_rejects_assistant_last_message(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("answer"))
        engine = build_engine(llm)

        await engine.run("task")

        with pytest.raises(ValueError, match="user or tool"):
            await engine.run(None)

    async def test_continuation_rejects_empty_conversation(self) -> None:
        engine = build_engine(FakeLLM())

        with pytest.raises(ValueError):
            await engine.run(None)

    async def test_abort_signal_is_forwarded_to_the_llm(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("answer"))
        engine = build_engine(llm)
        abort = threading.Event()

        await engine.run("task", abort=abort)

        assert llm.aborts == [abort]


class TestObservationStatus:
    """Observation 状态真实：错误信封判 error，工具异常收敛为 error 观察。"""

    async def test_error_envelope_produces_error_observation_in_history(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        llm.enqueue(*text_events("done"))
        engine = build_engine(llm, tools=[make_tool([], result=tool_error("E_FAIL", "disk full"))])

        await engine.run("task")

        tool_message = llm.requests[1].messages[-1]
        assert tool_message["role"] == "tool"
        assert "disk full" in tool_message["content"]


class TestReviewRegressions:
    """PR #72 审查回归：runaway 总闸、事件收束、abort 边界、失败参数保留。"""

    async def test_max_turns_guards_length_retry_runaway(self) -> None:
        """length 重发循环受 max_turns 总闸约束，不再无限续轮。"""
        llm = FakeLLM()
        for _ in range(10):
            llm.enqueue(*tool_call_events([("c1", "t", '{"partial')], stop="length"))
        engine = build_engine(llm, max_turns=3)
        result = await engine.run("task")
        assert result.outcome == "error"
        assert result.turns <= 3

    async def test_exception_still_emits_agent_end(self) -> None:
        """异常逃逸也发出 agent_end（事件协议收束），异常语义不变继续传播。"""

        class ExplodingLLM:
            def stream(self, request, *, abort=None):
                raise ValueError("stream ended without Done")

        sink = RecordingSink()
        engine = build_engine(FakeLLM(), sink=sink)
        engine._llm = ExplodingLLM()  # noqa: SLF001 — 注入异常源
        with pytest.raises(ValueError, match="stream ended"):
            await engine.run("task")
        assert isinstance(sink.events[-1], AgentEnd)

    async def test_abort_at_turn_boundary_stops_loop(self) -> None:
        """abort 在 turn 边界生效（粗粒度取消）。"""
        abort = threading.Event()
        abort.set()
        llm = FakeLLM()
        llm.enqueue(*text_events("hi"))
        engine = build_engine(llm)
        result = await engine.run("task", abort=abort)
        assert result.outcome == "aborted"

    async def test_failed_tool_calls_keep_raw_arguments(self) -> None:
        """判失败的 tool call 保留原始截断参数供诊断（finishTurn/UI 可见）。"""
        sink = RecordingSink()
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "t", '{"partial')], stop="length"))
        engine = build_engine(llm, sink=sink)
        await engine.run("task")
        ends = [e for e in sink.events if isinstance(e, ToolExecutionEnd)]
        assert ends and ends[-1].observation.arguments.get("raw")

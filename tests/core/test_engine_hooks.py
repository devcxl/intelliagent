"""turn 边界 hook 与 steering/follow-up 消息队列测试（pi-engine-principles §1、issue #57）。

覆盖 prepareRequest / prepareNextTurn / finishTurn 三个挂载点的时机与能力，
steer()（运行中插话）与 follow_up()（settle 前送达）的注入时机，以及队列消费模式。
"""

from __future__ import annotations

import pytest

from src.core.engine import Engine
from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, PluginHost
from src.core.turn_hooks import (
    FinishDecision,
    FinishTurnHook,
    NextTurnContext,
    NextTurnUpdate,
    PrepareNextTurnHook,
    PrepareRequestHook,
    RequestContext,
    TurnResult,
)
from tests.core.engine_support import (
    FakeLLM,
    build_engine,
    make_tool,
    text_events,
    tool_arguments,
    tool_call_events,
)
from tests.core.plugin_host.fakes import FakePlugin, build_manifest


class TestTurnBoundaryHooks:
    """turn 边界 hook：prepareRequest 每请求前注入；prepareNextTurn 可替换 model/context；finishTurn 可要求再跑。"""

    async def test_prepare_request_runs_before_every_request_with_ephemeral_injection(self) -> None:
        """prepareRequest 的注入只影响本次请求（投影语义），不写回引擎记录、不跨轮累积。"""
        injected: list[list[str]] = []

        async def prepare(request: RequestContext) -> None:
            request.messages.append({"role": "system", "content": "injected"})
            injected.append([str(message.get("content")) for message in request.messages])

        log: list[str] = []
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        llm.enqueue(*text_events("done"))
        engine = build_engine(llm, tools=[make_tool(log)], turn_hooks=[PrepareRequestHook(callback=prepare)])

        await engine.run("task")

        assert len(injected) == 2
        for request in llm.requests:
            markers = [message for message in request.messages if message.get("content") == "injected"]
            assert len(markers) == 1
        assert all(message.get("content") != "injected" for message in engine.messages)

    async def test_prepare_next_turn_receives_turn_result_and_replaces_model(self) -> None:
        seen: list[tuple[int, str]] = []

        async def prepare_next(context: NextTurnContext) -> NextTurnUpdate | None:
            seen.append((context.result.turn, context.result.message["role"]))
            assert context.result.observations[0].status == "success"
            assert context.turn == 2
            return NextTurnUpdate(model="fake/model-2")

        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        llm.enqueue(*text_events("done"))
        engine = build_engine(llm, tools=[make_tool([])], turn_hooks=[PrepareNextTurnHook(callback=prepare_next)])

        result = await engine.run("task")

        assert result.turns == 2
        assert seen == [(1, "assistant")]
        assert llm.requests[0].model == "fake/model"
        assert llm.requests[1].model == "fake/model-2"

    async def test_prepare_next_turn_can_replace_context(self) -> None:
        async def compact(context: NextTurnContext) -> NextTurnUpdate | None:
            return NextTurnUpdate(messages=[{"role": "user", "content": "summary only"}])

        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]))
        llm.enqueue(*text_events("done"))
        engine = build_engine(llm, tools=[make_tool([])], turn_hooks=[PrepareNextTurnHook(callback=compact)])

        await engine.run("task")

        assert llm.requests[1].messages == [{"role": "user", "content": "summary only"}]

    async def test_finish_turn_continue_forces_another_turn(self) -> None:
        seen: list[int] = []

        async def keep_going(result: TurnResult) -> FinishDecision:
            seen.append(result.turn)
            return "continue" if result.turn == 1 else None

        llm = FakeLLM()
        llm.enqueue(*text_events("one"))
        llm.enqueue(*text_events("two"))
        engine = build_engine(llm, turn_hooks=[FinishTurnHook(callback=keep_going)])

        result = await engine.run("task")

        assert result.turns == 2
        assert seen == [1, 2]

    async def test_finish_turn_invalid_decision_is_rejected(self) -> None:
        async def junk(result: TurnResult) -> FinishDecision:
            return "keep going"  # type: ignore[return-value]

        llm = FakeLLM()
        llm.enqueue(*text_events("one"))
        engine = build_engine(llm, turn_hooks=[FinishTurnHook(callback=junk)])

        with pytest.raises(TypeError, match="finish_turn"):
            await engine.run("task")

    async def test_turn_hooks_mount_via_hook_capability(self) -> None:
        """turn 边界 hook 经 CapabilityKind.HOOK 注册挂载——挂载点扩展即插件能力。"""
        seen: list[int] = []

        async def keep_going(result: TurnResult) -> FinishDecision:
            seen.append(result.turn)
            return "continue" if result.turn == 1 else None

        host = PluginHost()
        capability = CapabilityDeclaration(kind=CapabilityKind.HOOK, name="engine.finish_turn")
        manifest = build_manifest(name="turn-hooks", capabilities=(capability,))
        host.load(
            FakePlugin(
                manifest=manifest,
                providers={(CapabilityKind.HOOK, "engine.finish_turn"): FinishTurnHook(callback=keep_going)},
            )
        )
        llm = FakeLLM()
        llm.enqueue(*text_events("one"))
        llm.enqueue(*text_events("two"))
        engine = Engine.from_host(host, llm=llm, model="fake/model")

        result = await engine.run("task")

        assert result.turns == 2
        assert seen == [1, 2]


class TestSteeringQueue:
    """steer() 运行中插话：当前 turn 工具执行完后、下次请求前注入。"""

    async def test_steering_message_is_injected_before_next_request(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*tool_call_events([("c1", "rec", tool_arguments("a.txt"))]), on_start=lambda: engine.steer("改用 Python"))
        llm.enqueue(*text_events("ok"))
        engine = build_engine(llm, tools=[make_tool([])])

        result = await engine.run("task")

        assert result.turns == 2
        second = llm.requests[1].messages
        assert second[-2]["role"] == "tool"  # 插话在工具结果之后、下次请求之前
        assert second[-1] == {"role": "user", "content": "改用 Python"}

    async def test_steering_keeps_the_loop_alive_without_tool_calls(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("first"), on_start=lambda: engine.steer("等等"))
        llm.enqueue(*text_events("second"))
        engine = build_engine(llm)

        result = await engine.run("task")

        assert result.turns == 2
        assert llm.requests[1].messages[-1] == {"role": "user", "content": "等等"}

    async def test_one_at_a_time_mode_delivers_oldest_first(self) -> None:
        def interject() -> None:
            engine.steer("first")
            engine.steer("second")

        llm = FakeLLM()
        llm.enqueue(*text_events("one"), on_start=interject)
        llm.enqueue(*text_events("two"))
        llm.enqueue(*text_events("three"))
        engine = build_engine(llm, steering_mode="one-at-a-time")

        result = await engine.run("task")

        assert result.turns == 3
        assert llm.requests[1].messages[-1] == {"role": "user", "content": "first"}
        assert llm.requests[2].messages[-1] == {"role": "user", "content": "second"}


class TestFollowUpQueue:
    """follow_up() 在 agent 即将停止时注入：settle 前送达，同一 run 内继续跑。"""

    async def test_follow_up_is_delivered_when_agent_settles(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("done"), on_start=lambda: engine.follow_up("再检查一遍"))
        llm.enqueue(*text_events("rechecked"))
        engine = build_engine(llm)

        result = await engine.run("task")

        assert result.outcome == "settled"
        assert result.turns == 2
        assert llm.requests[1].messages[-1] == {"role": "user", "content": "再检查一遍"}
        assert llm.requests[1].messages[0] == {"role": "user", "content": "task"}

    async def test_follow_up_queued_before_run_is_delivered_at_settle(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("done"))
        llm.enqueue(*text_events("and more"))
        engine = build_engine(llm)
        engine.follow_up("continue please")

        result = await engine.run("task")

        assert result.turns == 2
        assert llm.requests[1].messages[-1] == {"role": "user", "content": "continue please"}

    async def test_hard_exit_ignores_pending_follow_ups(self) -> None:
        llm = FakeLLM()
        llm.enqueue(*text_events("boom", stop="error"))
        engine = build_engine(llm)
        engine.follow_up("more work")

        result = await engine.run("task")

        assert result.outcome == "error"
        assert len(llm.requests) == 1

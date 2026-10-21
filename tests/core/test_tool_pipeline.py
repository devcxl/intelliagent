"""工具流水线测试（TDD）：顺序、fail-closed、结果改写、真实状态与事件序列（ADR 0010、pi-engine-principles §5）。

流水线契约：prepareArguments → validate → beforeToolCall（fail-closed）→ execute → afterToolCall（可改写结果）。
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from src.core.agent_events import AgentEvent, ToolExecutionEnd, ToolExecutionStart
from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, PluginHost
from src.core.tool_pipeline import (
    AfterToolCallHook,
    BeforeToolCallHook,
    HookDecision,
    Observation,
    ToolCall,
    ToolPipeline,
    ToolRequest,
)
from src.core.turn_hooks import PrepareRequestHook, RequestContext
from src.plugins.basic_tools import BasicToolsPlugin, ToolSpec, tool_error, tool_success
from src.utils.path_policy import PathPolicy
from tests.core.plugin_host.fakes import FakePlugin, build_manifest

DEFAULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "count": {"type": "integer"},
        "flag": {"type": "boolean"},
    },
    "required": ["path"],
}


class RecordingSink:
    """把事件名追加到共享日志，供事件顺序断言。"""

    def __init__(self, log: list[str] | None = None) -> None:
        self.events: list[AgentEvent] = []
        self._log = log

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)
        if self._log is not None:
            self._log.append(type(event).__name__)


def make_tool(
    log: list[str],
    *,
    name: str = "echo",
    schema: dict[str, Any] | None = None,
    result: str | None = None,
    raises: Exception | None = None,
) -> ToolSpec:
    """构造记录副作用的 fake 工具：handler 执行时向共享日志追加 "execute"。"""

    async def handler(**kwargs: Any) -> str:
        log.append("execute")
        if raises is not None:
            raise raises
        return result if result is not None else tool_success(received=kwargs)

    return ToolSpec(name=name, description="test tool", parameters=schema or DEFAULT_SCHEMA, handler=handler)


def make_request(**arguments: Any) -> ToolRequest:
    """默认带合法 path 的调用请求；关键字参数覆盖或补充默认参数。"""
    return ToolRequest(tool_call_id="c1", name="echo", arguments={"path": "a.txt", **arguments})


class TestPipelineOrder:
    """流水线顺序：hook 围绕 execute；校验失败与 beforeToolCall 阻止都不执行（fail-closed）。"""

    async def test_hooks_run_around_execute_in_order(self) -> None:
        log: list[str] = []

        async def before(call: ToolCall) -> HookDecision | None:
            log.append("before")
            return None

        async def after(call: ToolCall, observation: Observation) -> Observation:
            log.append("after")
            return observation

        pipeline = ToolPipeline(
            tools={"echo": make_tool(log)},
            hooks=[BeforeToolCallHook(callback=before), AfterToolCallHook(callback=after)],
        )

        await pipeline.run(make_request())

        assert log == ["before", "execute", "after"]

    async def test_validation_failure_does_not_execute(self) -> None:
        log: list[str] = []
        pipeline = ToolPipeline(tools={"echo": make_tool(log)})

        observation = await pipeline.run(make_request(count="not-a-number"))

        assert observation.status == "error"
        assert "count" in (observation.error or "")
        assert "execute" not in log

    async def test_missing_required_argument_is_reported_in_detail(self) -> None:
        log: list[str] = []
        pipeline = ToolPipeline(tools={"echo": make_tool(log)})

        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="echo", arguments={"count": 1}))

        assert observation.status == "error"
        assert "path" in (observation.error or "")
        assert "required" in (observation.error or "")
        assert "execute" not in log

    async def test_before_tool_call_block_prevents_execution(self) -> None:
        log: list[str] = []

        async def deny(call: ToolCall) -> HookDecision | None:
            log.append("before")
            return HookDecision(block=True, reason="denied by policy")

        async def after(call: ToolCall, observation: Observation) -> Observation:
            log.append("after")
            return observation

        pipeline = ToolPipeline(
            tools={"echo": make_tool(log)},
            hooks=[BeforeToolCallHook(callback=deny), AfterToolCallHook(callback=after)],
        )

        observation = await pipeline.run(make_request())

        assert observation.status == "denied"
        assert observation.error == "denied by policy"
        assert log == ["before"]

    async def test_before_tool_call_exception_prevents_execution(self) -> None:
        log: list[str] = []

        async def explode(call: ToolCall) -> HookDecision | None:
            log.append("before")
            raise RuntimeError("hook broke")

        pipeline = ToolPipeline(tools={"echo": make_tool(log)}, hooks=[BeforeToolCallHook(callback=explode)])

        observation = await pipeline.run(make_request())

        assert observation.status == "error"
        assert "hook broke" in (observation.error or "")
        assert log == ["before"]

    async def test_after_tool_call_rewrite_applies(self) -> None:
        log: list[str] = []

        async def rewrite(call: ToolCall, observation: Observation) -> Observation:
            return replace(observation, content="rewritten", status="error", error="rewritten error")

        pipeline = ToolPipeline(tools={"echo": make_tool(log)}, hooks=[AfterToolCallHook(callback=rewrite)])

        observation = await pipeline.run(make_request())

        assert observation.content == "rewritten"
        assert observation.status == "error"
        assert observation.error == "rewritten error"
        assert "execute" in log

    async def test_after_tool_call_exception_degrades_to_error(self) -> None:
        log: list[str] = []

        async def explode(call: ToolCall, observation: Observation) -> Observation:
            raise RuntimeError("after broke")

        pipeline = ToolPipeline(tools={"echo": make_tool(log)}, hooks=[AfterToolCallHook(callback=explode)])

        observation = await pipeline.run(make_request())

        assert observation.status == "error"
        assert "after broke" in (observation.error or "")
        assert "execute" in log

    async def test_after_tool_call_returning_non_observation_degrades_to_error(self) -> None:
        async def wrong_type(call: ToolCall, observation: Observation) -> Observation:
            return "not an observation"  # type: ignore[return-value]

        pipeline = ToolPipeline(tools={"echo": make_tool([])}, hooks=[AfterToolCallHook(callback=wrong_type)])

        observation = await pipeline.run(make_request())

        assert observation.status == "error"
        assert "Observation" in (observation.error or "")

    async def test_unknown_tool_reports_error(self) -> None:
        pipeline = ToolPipeline(tools={})

        observation = await pipeline.run(make_request())

        assert observation.status == "error"
        assert "unknown tool" in observation.content


class TestPrepareArguments:
    """prepareArguments：修复模型畸形参数（JSON 字符串、双重编码），容错不裸抛。"""

    async def test_json_string_arguments_are_parsed(self) -> None:
        log: list[str] = []
        pipeline = ToolPipeline(tools={"echo": make_tool(log)})

        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="echo", arguments='{"path": "a.txt"}'))

        assert observation.status == "success"
        assert "execute" in log

    async def test_double_encoded_json_arguments_are_parsed(self) -> None:
        log: list[str] = []
        pipeline = ToolPipeline(tools={"echo": make_tool(log)})

        observation = await pipeline.run(
            ToolRequest(tool_call_id="c1", name="echo", arguments='"{\\"path\\": \\"a\\"}"')
        )

        assert observation.status == "success"
        assert "execute" in log

    async def test_empty_arguments_become_empty_object(self) -> None:
        log: list[str] = []
        schema: dict[str, Any] = {"type": "object", "properties": {}}
        pipeline = ToolPipeline(tools={"echo": make_tool(log, schema=schema)})

        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="echo", arguments=""))

        assert observation.status == "success"
        assert "execute" in log

    async def test_malformed_json_reports_error_without_execution(self) -> None:
        log: list[str] = []
        pipeline = ToolPipeline(tools={"echo": make_tool(log)})

        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="echo", arguments="{oops"))

        assert observation.status == "error"
        assert "JSON" in (observation.error or "")
        assert "execute" not in log

    async def test_non_object_json_reports_error(self) -> None:
        log: list[str] = []
        pipeline = ToolPipeline(tools={"echo": make_tool(log)})

        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="echo", arguments="[1, 2]"))

        assert observation.status == "error"
        assert "JSON object" in (observation.error or "")
        assert "execute" not in log

    async def test_scalar_strings_are_coerced_per_schema(self) -> None:
        log: list[str] = []
        pipeline = ToolPipeline(tools={"echo": make_tool(log)})

        observation = await pipeline.run(make_request(count="5", flag="true"))

        assert observation.status == "success"
        assert observation.arguments == {"path": "a.txt", "count": 5, "flag": True}


class TestObservationStatus:
    """Observation 携带真实状态：success / denied / error，不再硬编码 success。"""

    async def test_success_envelope_maps_to_success(self) -> None:
        pipeline = ToolPipeline(tools={"echo": make_tool([])})

        observation = await pipeline.run(make_request())

        assert observation.status == "success"
        assert observation.error is None

    async def test_error_envelope_maps_to_error_with_message(self) -> None:
        pipeline = ToolPipeline(tools={"echo": make_tool([], result=tool_error("BOOM", "boom"))})

        observation = await pipeline.run(make_request())

        assert observation.status == "error"
        assert observation.error == "boom"

    async def test_handler_exception_maps_to_error(self) -> None:
        pipeline = ToolPipeline(tools={"echo": make_tool([], raises=ValueError("kaboom"))})

        observation = await pipeline.run(make_request())

        assert observation.status == "error"
        assert "kaboom" in (observation.error or "")

    async def test_provider_exception_outside_tool_spec_maps_to_error(self) -> None:
        class BrokenProvider:
            name = "echo"
            parameters = DEFAULT_SCHEMA

            async def run(self, **kwargs: Any) -> str:
                raise ValueError("provider kaboom")

        pipeline = ToolPipeline(tools={"echo": BrokenProvider()})

        observation = await pipeline.run(make_request())

        assert observation.status == "error"
        assert "provider kaboom" in (observation.error or "")

    async def test_denied_observation_carries_real_status(self) -> None:
        async def deny(call: ToolCall) -> HookDecision | None:
            return HookDecision(block=True, reason="no permission")

        pipeline = ToolPipeline(tools={"echo": make_tool([])}, hooks=[BeforeToolCallHook(callback=deny)])

        observation = await pipeline.run(make_request())

        assert observation.status == "denied"
        assert observation.error == "no permission"

    async def test_observation_carries_call_identity_and_duration(self) -> None:
        pipeline = ToolPipeline(tools={"echo": make_tool([])})

        observation = await pipeline.run(make_request())

        assert observation.tool_call_id == "c1"
        assert observation.name == "echo"
        assert observation.duration_ms >= 0.0


class TestPipelineEvents:
    """事件序列：tool_execution_start 先于副作用；start/end 括住每次流水线执行。"""

    async def test_tool_execution_start_precedes_side_effects(self) -> None:
        log: list[str] = []
        sink = RecordingSink(log)
        pipeline = ToolPipeline(tools={"echo": make_tool(log)}, sink=sink)

        await pipeline.run(make_request())

        assert log == ["ToolExecutionStart", "execute", "ToolExecutionEnd"]

    async def test_tool_execution_end_carries_observation(self) -> None:
        sink = RecordingSink()
        pipeline = ToolPipeline(tools={"echo": make_tool([])}, sink=sink)

        observation = await pipeline.run(make_request())

        end = sink.events[-1]
        assert isinstance(end, ToolExecutionEnd)
        assert end.observation is observation
        assert end.observation.status == "success"

    async def test_events_bracket_failed_call(self) -> None:
        sink = RecordingSink()
        pipeline = ToolPipeline(tools={"echo": make_tool([])}, sink=sink)

        observation = await pipeline.run(make_request(count="bad"))

        assert [type(event) for event in sink.events] == [ToolExecutionStart, ToolExecutionEnd]
        end = sink.events[-1]
        assert isinstance(end, ToolExecutionEnd)
        assert end.observation is observation
        assert end.observation.status == "error"


class TestHookChain:
    """hook 链式调用：同一挂载点按注册顺序依次执行，before 首个 block 短路，after 逐个改写。"""

    async def test_multiple_before_hooks_run_in_order(self) -> None:
        log: list[str] = []

        def before_hook(marker: str) -> BeforeToolCallHook:
            async def callback(call: ToolCall) -> HookDecision | None:
                log.append(marker)
                return None

            return BeforeToolCallHook(callback=callback)

        pipeline = ToolPipeline(tools={"echo": make_tool(log)}, hooks=[before_hook("h1"), before_hook("h2")])

        await pipeline.run(make_request())

        assert log == ["h1", "h2", "execute"]

    async def test_before_chain_short_circuits_on_first_block(self) -> None:
        log: list[str] = []

        async def deny(call: ToolCall) -> HookDecision | None:
            log.append("h1")
            return HookDecision(block=True, reason="stop")

        async def never(call: ToolCall) -> HookDecision | None:
            log.append("h2")
            return None

        pipeline = ToolPipeline(
            tools={"echo": make_tool(log)},
            hooks=[BeforeToolCallHook(callback=deny), BeforeToolCallHook(callback=never)],
        )

        await pipeline.run(make_request())

        assert log == ["h1"]

    async def test_after_hooks_chain_rewrites_in_order(self) -> None:
        def after_hook(marker: str) -> AfterToolCallHook:
            async def callback(call: ToolCall, observation: Observation) -> Observation:
                return replace(observation, content=f"{observation.content}|{marker}")

            return AfterToolCallHook(callback=callback)

        pipeline = ToolPipeline(
            tools={"echo": make_tool([], result="base")},
            hooks=[after_hook("h1"), after_hook("h2")],
        )

        observation = await pipeline.run(make_request())

        assert observation.content == "base|h1|h2"


class TestHookCapabilityContract:
    """hook 契约：CapabilityKind.HOOK 提供者的注册形态，由流水线按注册顺序链式调用。"""

    @staticmethod
    def load_hook_plugin(host: PluginHost, plugin_name: str, capability_name: str, provider: object) -> None:
        capability = CapabilityDeclaration(kind=CapabilityKind.HOOK, name=capability_name)
        manifest = build_manifest(name=plugin_name, capabilities=(capability,))
        host.load(FakePlugin(manifest=manifest, providers={(CapabilityKind.HOOK, capability_name): provider}))

    async def test_hooks_collected_from_host_chain_in_load_order(self) -> None:
        log: list[str] = []

        def hook(marker: str) -> BeforeToolCallHook:
            async def callback(call: ToolCall) -> HookDecision | None:
                log.append(marker)
                return None

            return BeforeToolCallHook(callback=callback)

        host = PluginHost()
        self.load_hook_plugin(host, "hook-one", "hook.h1", hook("h1"))
        self.load_hook_plugin(host, "hook-two", "hook.h2", hook("h2"))
        tool_capability = CapabilityDeclaration(kind=CapabilityKind.TOOL, name="echo")
        tool_manifest = build_manifest(name="echo-tool", capabilities=(tool_capability,))
        host.load(FakePlugin(manifest=tool_manifest, providers={(CapabilityKind.TOOL, "echo"): make_tool(log)}))
        pipeline = ToolPipeline.from_host(host)

        observation = await pipeline.run(make_request())

        assert log == ["h1", "h2", "execute"]
        assert observation.status == "success"

    def test_from_host_rejects_non_hook_provider(self) -> None:
        host = PluginHost()
        self.load_hook_plugin(host, "bogus-hook", "hook.bogus", object())

        with pytest.raises(TypeError, match="hook.bogus"):
            ToolPipeline.from_host(host)


class TestBasicToolsIntegration:
    """流水线接真实 ToolSpec：PluginHost 组装，read 工具走完整流水线产出 success 观察。"""

    async def test_pipeline_runs_real_read_tool_from_host(self, tmp_path: Path) -> None:
        target = tmp_path / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")
        host = PluginHost()
        host.load(BasicToolsPlugin(path_policy=PathPolicy(workspace=tmp_path)))
        pipeline = ToolPipeline.from_host(host)

        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="read", arguments={"path": str(target)}))

        assert observation.status == "success"
        assert "hello" in observation.content


class TestReviewRegressions:
    """PR #71 审查回归：fail-closed 完整性、事件值语义、非法输入收敛。"""

    async def test_before_hook_returning_junk_yields_error_observation(self) -> None:
        """before hook 返回非 HookDecision：产出 error 观察 + 事件完整，不裸抛破缺协议。"""

        class JunkHook:
            async def __call__(self, call):
                return "not a decision"

        pipeline = ToolPipeline(
            tools={"t": make_tool([])},
            hooks=[BeforeToolCallHook(callback=JunkHook())],
            sink=RecordingSink(),
        )
        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="t", arguments={"path": "a.txt"}))
        assert observation.status == "error"
        assert "non-HookDecision" in (observation.error or "")

    def test_constructor_rejects_unknown_hook_provider(self) -> None:
        """未知 hook 提供者必须显式拒绝——静默丢弃即 fail-open。"""

        class Stranger:
            pass

        with pytest.raises(TypeError, match="unsupported hook provider"):
            ToolPipeline(tools={}, hooks=[Stranger()])  # type: ignore[list-item]

    async def test_events_hold_argument_snapshots(self) -> None:
        """事件持有的 arguments 是快照：事后 mutate 不篡改已发事件（协议值语义）。"""
        sink = RecordingSink()
        arguments = {"path": "a.txt"}
        pipeline = ToolPipeline(tools={"t": make_tool([])}, sink=sink)
        await pipeline.run(ToolRequest(tool_call_id="c1", name="t", arguments=arguments))
        arguments["path"] = "mutated.txt"
        start = [e for e in sink.events if isinstance(e, ToolExecutionStart)][0]
        assert start.arguments == {"path": "a.txt"}

    async def test_non_mapping_arguments_yield_error_observation(self) -> None:
        """非 str/Mapping 输入收敛为 error 观察，不裸抛。"""
        pipeline = ToolPipeline(tools={"t": make_tool([])})
        observation = await pipeline.run(ToolRequest(tool_call_id="c1", name="t", arguments=None))  # type: ignore[arg-type]
        assert observation.status == "error"
        assert "must be a mapping or JSON string" in (observation.error or "")


class TestTurnHookPassThrough:
    """turn 边界 hook（T7b）与工具 hook 同走 CapabilityKind.HOOK：流水线跳过它们，未知形态仍显式拒绝。"""

    async def test_from_host_passes_turn_hooks_without_running_them_in_the_tool_chain(self) -> None:
        calls: list[str] = []

        async def prepare(request: RequestContext) -> None:
            calls.append("prepare_request")

        host = PluginHost()
        tool_capability = CapabilityDeclaration(kind=CapabilityKind.TOOL, name="echo")
        hook_capability = CapabilityDeclaration(kind=CapabilityKind.HOOK, name="engine.prepare_request")
        host.load(FakePlugin(manifest=build_manifest(name="echo-tool", capabilities=(tool_capability,)),
                             providers={(CapabilityKind.TOOL, "echo"): make_tool([])}))
        host.load(FakePlugin(manifest=build_manifest(name="turn-hooks", capabilities=(hook_capability,)),
                             providers={(CapabilityKind.HOOK, "engine.prepare_request"): PrepareRequestHook(callback=prepare)}))
        pipeline = ToolPipeline.from_host(host)

        observation = await pipeline.run(make_request())

        assert observation.status == "success"
        assert calls == []

    async def test_result_envelope_terminate_flag_lands_on_observation(self) -> None:
        """工具经结果信封 {"status": "ok", "terminate": true} 请求终止；默认 False。"""
        pipeline = ToolPipeline(tools={"t": make_tool([], result=tool_success(terminate=True))})
        observation = await pipeline.run(make_request())
        assert observation.terminate is True

        pipeline = ToolPipeline(tools={"t": make_tool([])})
        observation = await pipeline.run(make_request())
        assert observation.terminate is False

"""工具执行流水线与 hook 契约（ADR 0010、pi-engine-principles §5）。

单次工具调用的完整路径：

    prepareArguments → validate → beforeToolCall（fail-closed）→ execute → afterToolCall（可改写结果）

- prepareArguments：修复模型畸形参数（JSON 字符串、双重编码 JSON 文本），容错收敛为参数对象或诊断。
- validate：JSON Schema 校验 + 标量 coerce（"5"→5），失败给字段级详细错误。
- beforeToolCall：hook 能力（CapabilityKind.HOOK）链式调用；返回 block 或抛错即工具不执行（fail-closed）。
- execute：调用 Tool 能力提供者（ToolSpec 结构性满足 ToolProvider）。
- afterToolCall：hook 链式改写结果 content/status/error；仅在 execute 之后运行。

事件经 EventSink 按协议发出（src.core.agent_events）：tool_execution_start 在任何副作用前发出
（permission 拦截与"执行中"状态的基础），tool_execution_end 携带 Observation——status 是真实状态
（success/denied/error），不再硬编码 success。
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal, Protocol, cast

from jsonschema import SchemaError, ValidationError
from jsonschema import validate as jsonschema_validate

from src.core.agent_events import AgentEvent, EventSink, ToolExecutionEnd, ToolExecutionStart
from src.core.plugin_host import CapabilityKind, PluginHost

ObservationStatus = Literal["success", "denied", "error"]
"""Observation 的真实状态：success 执行成功 / denied 被 hook 阻止 / error 校验、执行或 hook 故障。"""


@dataclass(frozen=True)
class ToolRequest:
    """模型请求的一次工具调用（流水线输入）：arguments 可能是畸形 JSON 文本，由 prepareArguments 修复。"""

    tool_call_id: str
    name: str
    arguments: str | Mapping[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """已通过 prepare 与 validate 的工具调用视图：hook 与执行的共同输入。"""

    tool_call_id: str
    name: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class Observation:
    """一次工具执行的结果记录（CONTEXT 术语：Observation）。

    content 是给模型看的结果文本，error 是给 UI 与日志的诊断；status 见 ObservationStatus。
    """

    tool_call_id: str
    name: str
    arguments: Mapping[str, Any]
    content: str
    status: ObservationStatus
    error: str | None = None
    duration_ms: float = 0.0


@dataclass(frozen=True)
class HookDecision:
    """beforeToolCall 的裁决：block=True 表示阻止执行，reason 供 UI 与模型诊断。"""

    block: bool = False
    reason: str | None = None


class BeforeToolCall(Protocol):
    """beforeToolCall 挂载回调（permission 插件形态）。

    返回 HookDecision(block=True) 或抛出异常都表示阻止执行（fail-closed）：工具绝不运行；
    显式 block 产出 denied 观察，抛错产出 error 观察。
    返回 None 或 HookDecision(block=False) 表示放行，链上后续 hook 继续裁决。
    """

    async def __call__(self, call: ToolCall) -> HookDecision | None: ...


class AfterToolCall(Protocol):
    """afterToolCall 挂载回调（memory 插件形态）。

    返回改写后的 Observation（可改 content/status/error）；链上后一个 hook 看到前一个的改写结果。
    回调抛错或返回非 Observation 时结果降级为 error 观察（工具已执行，不可回滚）。
    """

    async def __call__(self, call: ToolCall, observation: Observation) -> Observation: ...


@dataclass(frozen=True)
class BeforeToolCallHook:
    """beforeToolCall 挂载点的 hook 能力提供者（CONTEXT 术语：Hook）：注册为 CapabilityKind.HOOK。"""

    callback: BeforeToolCall


@dataclass(frozen=True)
class AfterToolCallHook:
    """afterToolCall 挂载点的 hook 能力提供者（CONTEXT 术语：Hook）：注册为 CapabilityKind.HOOK。"""

    callback: AfterToolCall


HookProvider = BeforeToolCallHook | AfterToolCallHook
"""hook 能力提供者的两种形态，按挂载点区分。"""


class ToolProvider(Protocol):
    """Tool 能力提供者的最小契约（ToolSpec 结构性满足）：能力名、参数 JSON Schema、异步执行。

    结果信封约定（Observation 真实状态的判定依据，US21）：
    - 返回统一信封 ``{"status": "ok", ...}`` / ``{"status": "error", "error": ...}``（basic_tools 同款）；
    - 顶层 ``status: "error"`` 判 error 并提取 error 字段，其余判 success；
    - 抛异常一律判 error。返回裸文本/数据而不守信封的工具，其失败状态不可判定——契约要求守信封。
    """

    name: str
    parameters: Mapping[str, Any]

    async def run(self, **kwargs: Any) -> str: ...


class ToolPipeline:
    """工具调用流水线：顺序固定、fail-closed、事件按协议发出，Observation 携带真实状态。

    同一挂载点的多个 hook 按传入顺序链式执行：before 链首个 block/异常短路，after 链逐个改写结果。
    """

    def __init__(
        self,
        tools: Mapping[str, ToolProvider],
        hooks: Sequence[HookProvider] = (),
        *,
        sink: EventSink | None = None,
    ) -> None:
        self._tools = dict(tools)
        for hook in hooks:
            if not isinstance(hook, (BeforeToolCallHook, AfterToolCallHook)):
                # 静默丢弃即 fail-open（被剔除的 permission 钩子不再拦截），必须显式拒绝
                raise TypeError(f"unsupported hook provider type: {type(hook).__name__}")
        self._before_hooks = tuple(hook for hook in hooks if isinstance(hook, BeforeToolCallHook))
        self._after_hooks = tuple(hook for hook in hooks if isinstance(hook, AfterToolCallHook))
        self._sink = sink

    @classmethod
    def from_host(cls, host: PluginHost, *, sink: EventSink | None = None) -> ToolPipeline:
        """从 PluginHost 组装流水线：Tool 能力提供者作为可执行工具，Hook 能力提供者按注册顺序链式挂载。"""
        tools = {
            name: cast(ToolProvider, provider) for name, provider in host.capabilities(CapabilityKind.TOOL).items()
        }
        return cls(tools=tools, hooks=_hook_providers(host), sink=sink)

    async def run(self, request: ToolRequest) -> Observation:
        """执行一次工具调用的完整流水线，返回 Observation。

        tool_execution_start 在任何副作用前发出，tool_execution_end 携带最终（含改写后）的 Observation。
        """
        started = time.perf_counter()
        self._emit(
            ToolExecutionStart(
                tool_call_id=request.tool_call_id,
                name=request.name,
                arguments=_freeze_arguments(request.arguments),
            )
        )
        observation = replace(await self._process(request), duration_ms=(time.perf_counter() - started) * 1000)
        self._emit(ToolExecutionEnd(tool_call_id=request.tool_call_id, observation=observation))
        return observation

    async def _process(self, request: ToolRequest) -> Observation:
        tool = self._tools.get(request.name)
        if tool is None:
            return _error_observation(request.tool_call_id, request.name, f"unknown tool '{request.name}'")
        arguments, prepare_error = _prepare_arguments(request.arguments)
        if prepare_error is not None:
            return _error_observation(request.tool_call_id, request.name, prepare_error)
        validated, validate_error = _validate_arguments(tool.parameters, arguments)
        if validate_error is not None:
            return _error_observation(request.tool_call_id, request.name, validate_error, arguments)
        call = ToolCall(tool_call_id=request.tool_call_id, name=request.name, arguments=_freeze_arguments(validated))
        blocked = await self._before(call)
        if blocked is not None:
            return blocked
        return await self._after(call, await self._execute(tool, call))

    async def _before(self, call: ToolCall) -> Observation | None:
        """链式执行 beforeToolCall：返回 None 放行，返回 Observation 即终止结果（fail-closed）。

        显式 block 产出 denied 观察，hook 异常或返回非 HookDecision 产出 error 观察——两者都不执行工具。
        """
        for hook in self._before_hooks:
            try:
                decision = await hook.callback(call)
            except Exception as exc:
                return _error_observation(
                    call.tool_call_id, call.name, f"before_tool_call hook failed: {exc}", call.arguments
                )
            if decision is not None and not isinstance(decision, HookDecision):
                return _error_observation(
                    call.tool_call_id,
                    call.name,
                    "before_tool_call hook returned a non-HookDecision result",
                    call.arguments,
                )
            if decision is not None and decision.block:
                return _denied_observation(call, decision.reason or "tool call blocked by a before_tool_call hook")
        return None

    async def _execute(self, tool: ToolProvider, call: ToolCall) -> Observation:
        """执行工具：任何异常都收敛为 error 观察，绝不裸抛到引擎。"""
        try:
            content = await tool.run(**dict(call.arguments))
        except Exception as exc:
            return _error_observation(call.tool_call_id, call.name, f"tool execution failed: {exc}", call.arguments)
        status, error = _result_status(content)
        return Observation(
            tool_call_id=call.tool_call_id,
            name=call.name,
            arguments=call.arguments,
            content=content,
            status=status,
            error=error,
        )

    async def _after(self, call: ToolCall, observation: Observation) -> Observation:
        """链式执行 afterToolCall：逐个改写结果；回调异常或返回非 Observation 时降级为 error 观察。"""
        current = observation
        for hook in self._after_hooks:
            try:
                rewritten = await hook.callback(call, current)
            except Exception as exc:
                return _error_observation(
                    call.tool_call_id, call.name, f"after_tool_call hook failed: {exc}", call.arguments
                )
            if not isinstance(rewritten, Observation):
                return _error_observation(
                    call.tool_call_id,
                    call.name,
                    "after_tool_call hook returned a non-Observation result",
                    call.arguments,
                )
            current = rewritten
        return current

    def _emit(self, event: AgentEvent) -> None:
        if self._sink is not None:
            self._sink.emit(event)


def _freeze_arguments(arguments: str | Mapping[str, Any]) -> str | Mapping[str, Any]:
    """事件/观察持有的 arguments 必须是快照：外部事后 mutate 不得篡改已发事件（协议值语义）。"""
    return dict(arguments) if isinstance(arguments, Mapping) else arguments


def _prepare_arguments(raw: str | Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """prepareArguments：修复模型畸形参数。返回 (参数对象, None) 或 (None, 诊断信息)。

    修复范围：JSON 字符串参数、双重编码的 JSON 文本、空参数。字段重命名需要别名元数据，契约不提供。
    """
    if isinstance(raw, Mapping):
        return dict(raw), None
    if not isinstance(raw, str):
        return None, f"tool arguments must be a mapping or JSON string, got {type(raw).__name__}"
    text = raw.strip()
    if not text:
        return {}, None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"arguments are not valid JSON: {exc.msg}"
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError as exc:
            return None, f"arguments are not valid JSON: {exc.msg}"
    if not isinstance(parsed, Mapping):
        return None, f"arguments must be a JSON object, got {type(parsed).__name__}"
    return dict(parsed), None


def _validate_arguments(
    schema: Mapping[str, Any], arguments: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, str | None]:
    """validate：按工具 JSON Schema 校验并 coerce 标量。返回 (修复后的参数, None) 或 (None, 字段级诊断)。"""
    coerced = _coerce_arguments(schema, arguments)
    try:
        jsonschema_validate(instance=coerced, schema=dict(schema))
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.absolute_path) or "<root>"
        return None, f"argument validation failed at '{path}': {exc.message}"
    except SchemaError as exc:
        return None, f"tool schema is invalid: {exc.message}"
    return coerced, None


def _coerce_arguments(schema: Mapping[str, Any], arguments: Mapping[str, Any]) -> dict[str, Any]:
    """按 schema 的 properties 对参数做递归 coerce；未声明的键原样保留，交给校验器裁决。"""
    properties = schema.get("properties")
    if not isinstance(properties, Mapping):
        return dict(arguments)
    return {
        key: _coerce_value(properties[key], value) if key in properties else value for key, value in arguments.items()
    }


def _coerce_value(schema: Mapping[str, Any], value: Any) -> Any:
    """递归 coerce：object 按 properties、array 按 items、字符串标量按声明类型修复。"""
    if isinstance(value, Mapping):
        return _coerce_arguments(schema, value)
    if isinstance(value, list):
        items = schema.get("items")
        if not isinstance(items, Mapping):
            return value
        return [_coerce_value(items, item) for item in value]
    return _coerce_scalar(schema.get("type"), value)


def _coerce_scalar(declared: Any, value: Any) -> Any:
    """把字符串标量修回声明类型（模型常把 5 传成 "5"）；修不回的原样保留，交给校验器给出字段级错误。"""
    if not isinstance(value, str):
        return value
    types = {declared} if isinstance(declared, str) else set(declared) if isinstance(declared, list) else set()
    if not types or "string" in types:
        return value
    text = value.strip()
    if "boolean" in types and text.lower() in ("true", "false"):
        return text.lower() == "true"
    if "integer" in types:
        try:
            return int(text)
        except ValueError:
            pass
    if "number" in types:
        try:
            return float(text)
        except ValueError:
            pass
    return value


def _result_status(content: str) -> tuple[ObservationStatus, str | None]:
    """从工具结果信封推导真实状态（basic_tools 统一信封 {"status": "ok"/"error"}）；非信封内容视为成功。"""
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return "success", None
    if isinstance(payload, Mapping) and payload.get("status") == "error":
        return "error", str(payload.get("error") or "tool reported an error without a message")
    return "success", None


def _error_observation(
    tool_call_id: str, name: str, message: str, arguments: Mapping[str, Any] | None = None
) -> Observation:
    """流水线拒绝或执行失败时的 error 观察：content 与 error 都携带可诊断信息。"""
    return Observation(
        tool_call_id=tool_call_id,
        name=name,
        arguments=dict(arguments or {}),
        content=message,
        status="error",
        error=message,
    )


def _denied_observation(call: ToolCall, reason: str) -> Observation:
    """beforeToolCall 阻止执行时的 denied 观察：content 告知模型原因，error 供 UI 与日志诊断。"""
    return Observation(
        tool_call_id=call.tool_call_id,
        name=call.name,
        arguments=call.arguments,
        content=f"tool call denied: {reason}",
        status="denied",
        error=reason,
    )


def _hook_providers(host: PluginHost) -> tuple[HookProvider, ...]:
    """收集宿主中全部 hook 能力提供者（CapabilityKind.HOOK），保持注册顺序。"""
    hooks: list[HookProvider] = []
    for name, provider in host.capabilities(CapabilityKind.HOOK).items():
        if not isinstance(provider, (BeforeToolCallHook, AfterToolCallHook)):
            raise TypeError(
                f"hook capability '{name}' must provide BeforeToolCallHook or AfterToolCallHook, "
                f"got {type(provider).__name__}"
            )
        hooks.append(provider)
    return tuple(hooks)

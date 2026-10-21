"""引擎循环状态机：双层循环把一个任务跑到收束（ADR 0010、pi-engine-principles §1）。

外层循环：follow-up 队列与显式 continuation——agent 停止后又有消息就继续跑；
内层循环：一个 assistant 响应 + 其 tool calls/results + steering 消息，直到没有要执行的工具调用。

一个 turn 的顺序（turn_start / turn_end 事件划分边界）：

    prepareRequest → 流式响应（message_* 事件）→ stopReason 分类 → 工具流水线 → 提交 →
    turn_end → finishTurn → prepareNextTurn → 循环判定

stopReason 三分类（pi 同型）：

- error / aborted：硬退出——不执行工具、不跑 turn 边界 hook，turn_end + agent_end 收束；
  assistant 的 tool_calls 用"未执行"错误结果配对提交，历史绝不留下未配对记录（旧引擎 P0 缺陷）。
- length：输出被 token 上限截断，tool call 参数必然不完整——本轮所有 tool call 判失败（不执行），
  产出 error 观察让模型重发完整参数，循环继续。
- stop：正常执行工具。

终止信号：一个批次的全部 Observation 都带 terminate 才停循环（pi 语义）；error/aborted 硬退出优先。

steer() 的消息在下一次请求组装前注入（运行中插话）；follow_up() 的消息在外层循环的 settle 点注入
（agent 即将停止时接上新任务）。判失败（未执行）的 tool call 也发出 tool_execution_start/end
（end 携带 error 观察），事件流保持配对完整——但工具绝不运行。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from src.core.agent_events import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    EventSink,
    MessageEnd,
    MessageUpdate,
    RunOutcome,
    ToolExecutionEnd,
    ToolExecutionStart,
    TurnEnd,
    TurnStart,
    message_events,
)
from src.core.async_stream import iterate_in_thread
from src.core.pending_messages import PendingMessageQueue, QueueMode
from src.core.plugin_host import CapabilityKind, PluginHost
from src.core.tool_calls import ToolCallBuilder
from src.core.tool_pipeline import Observation, ToolPipeline, ToolProvider, ToolRequest
from src.core.turn_hooks import (
    FinishDecision,
    FinishTurnHook,
    NextTurnContext,
    NextTurnUpdate,
    PrepareNextTurnHook,
    PrepareRequestHook,
    RequestContext,
    TurnHookProvider,
    TurnResult,
)
from src.llm.stream import (
    ChatMessage,
    LLMClient,
    LLMEvent,
    StopReason,
    StreamRequest,
    TextDelta,
    ToolCallDelta,
    ToolSchema,
)

NOT_EXECUTED = "tool call was not executed: run stopped with stop reason '{reason}'"
TRUNCATED = (
    "tool call arguments were truncated by the output token limit (stop reason 'length') and were not executed; "
    "call the tool again with complete arguments"
)


@dataclass(frozen=True)
class RunResult:
    """一次 run 的收束结果（agent_end 的机器可读形态）。"""

    outcome: RunOutcome
    turns: int
    stop_reason: StopReason | None


def tool_schemas(providers: Mapping[str, ToolProvider]) -> list[ToolSchema]:
    """把 Tool 能力提供者转成模型可见的 function calling schema（原生 JSON Schema 全量透传）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": provider.name,
                "description": provider.description,
                "parameters": dict(provider.parameters),
            },
        }
        for provider in providers.values()
    ]


class Engine:
    """引擎（CONTEXT 术语：Engine）：消费 LLM 流、执行工具调用、驱动 Conversation 到收束。

    依赖全部显式注入：LLM 客户端、工具流水线、模型可见的工具 schema、turn 边界 hook、事件出口。
    Conversation 记录在引擎内 append-only 累积；投影式压缩由运行时注入的 prepareNextTurn hook 换入。
    """

    def __init__(
        self,
        llm: LLMClient,
        pipeline: ToolPipeline,
        tools: Sequence[ToolSchema],
        *,
        model: str,
        hooks: Sequence[TurnHookProvider] = (),
        sink: EventSink | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_turns: int = 50,
        steering_mode: QueueMode = "all",
        follow_up_mode: QueueMode = "all",
    ) -> None:
        self._llm = llm
        self._pipeline = pipeline
        self._tool_schemas = list(tools)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._max_turns = max_turns
        self._sink = sink
        for hook in hooks:
            if not isinstance(hook, (PrepareRequestHook, PrepareNextTurnHook, FinishTurnHook)):
                raise TypeError(f"unsupported turn hook provider type: {type(hook).__name__}")
        self._prepare_request_hooks = tuple(hook for hook in hooks if isinstance(hook, PrepareRequestHook))
        self._prepare_next_turn_hooks = tuple(hook for hook in hooks if isinstance(hook, PrepareNextTurnHook))
        self._finish_turn_hooks = tuple(hook for hook in hooks if isinstance(hook, FinishTurnHook))
        self._steering = PendingMessageQueue(steering_mode)
        self._follow_ups = PendingMessageQueue(follow_up_mode)
        self._messages: list[ChatMessage] = []
        self._turn_seq = 0
        self._message_seq = 0
        self._running = False

    @classmethod
    def from_host(
        cls,
        host: PluginHost,
        *,
        llm: LLMClient,
        model: str,
        sink: EventSink | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_turns: int = 50,
        steering_mode: QueueMode = "all",
        follow_up_mode: QueueMode = "all",
        extra_hooks: Sequence[TurnHookProvider] = (),
    ) -> Engine:
        """从 PluginHost 组装引擎：Tool 能力进工具流水线，Hook 能力按形态分流到工具链与 turn 边界。

        extra_hooks 由组合根注入（如 Compactor 的 prepareRequest/prepareNextTurn），
        先于宿主 Hook 执行——压缩投影必须先于注入类 hook 改写请求视图。
        """
        pipeline = ToolPipeline.from_host(host, sink=sink)
        tools = tool_schemas(cast(Mapping[str, ToolProvider], host.capabilities(CapabilityKind.TOOL)))
        host_hooks = [
            hook for hook in host.capabilities(CapabilityKind.HOOK).values() if isinstance(hook, TurnHookProvider)
        ]
        hooks = [*extra_hooks, *host_hooks]
        return cls(
            llm,
            pipeline,
            tools,
            model=model,
            hooks=hooks,
            sink=sink,
            temperature=temperature,
            max_tokens=max_tokens,
            max_turns=max_turns,
            steering_mode=steering_mode,
            follow_up_mode=follow_up_mode,
        )

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        """当前 Conversation 的消息记录（append-only，返回快照）。"""
        return tuple(dict(message) for message in self._messages)

    def steer(self, message: str) -> None:
        """运行中插话：在下一次请求组装前注入（当前 turn 工具执行完后、下次请求前）。"""
        self._steering.push(message)

    def follow_up(self, message: str) -> None:
        """后续任务：在 agent 即将停止时注入，外层循环接上继续跑。"""
        self._follow_ups.push(message)

    async def run(self, task: str | None = None, *, abort: threading.Event | None = None) -> RunResult:
        """跑一个 Run：task 进入 Conversation 后执行双层循环直到收束。

        task 为 None 表示显式 continuation（pi agentLoopContinue）：不加新消息、从现有上下文续跑，
        要求最后一条消息是 user 输入或 tool 结果。
        """
        if self._running:
            raise RuntimeError("engine is already running")
        self._running = True
        try:
            if task is not None:
                self._messages.append({"role": "user", "content": task})
            else:
                self._require_continuation_point()
            self._emit(AgentStart())
            try:
                result = await self._run_loops(abort)
            except BaseException as exc:
                # 事件协议收束：异常逃逸也发出 agent_end（前端不悬挂）；异常语义不变，继续传播。
                self._emit(AgentEnd(outcome="error"))
                raise exc
            self._emit(AgentEnd(outcome=result.outcome))
            return result
        finally:
            self._running = False

    async def _run_loops(self, abort: threading.Event | None) -> RunResult:
        """外层循环：内层收束后接 follow-up 继续跑；硬退出（error/aborted/terminated）直接收束。

        总闸：累计 turn 数超过 max_turns 即以 error 收束——length 重发循环、finishTurn
        无限 continue、follow_up 无限接续三条 runaway 路径都受此约束。
        """
        turns = 0
        outcome: RunOutcome = "settled"
        stop_reason: StopReason | None = None
        while True:
            inner = await self._run_inner(abort)
            turns += inner.turns
            outcome, stop_reason = inner.outcome, inner.stop_reason
            if outcome != "settled":
                break
            if turns >= self._max_turns:
                outcome, stop_reason = "error", "error"
                break
            if abort is not None and abort.is_set():
                outcome, stop_reason = "aborted", "aborted"
                break
            follow_ups = self._follow_ups.drain()
            if not follow_ups:
                break
            self._messages.extend({"role": "user", "content": message} for message in follow_ups)
        return RunResult(outcome=outcome, turns=turns, stop_reason=stop_reason)

    async def _run_inner(self, abort: threading.Event | None) -> _InnerOutcome:
        """内层循环：一个 assistant 响应 + 其工具结果算一个 turn，直到没有要执行的工具调用。

        abort 检查粒度：turn 边界（工具执行中不中断——粗粒度取消，pi 同型）。
        max_turns 同样约束内层续轮（length 重发循环的 runaway 在此被闸）。
        """
        turns = 0
        while True:
            if abort is not None and abort.is_set():
                return _InnerOutcome("aborted", turns, "aborted")
            if turns >= self._max_turns:
                return _InnerOutcome("error", turns, "error")
            turns += 1
            self._turn_seq += 1
            self._emit(TurnStart(turn=self._turn_seq))
            record = await self._run_turn(self._turn_seq, abort)
            self._emit(TurnEnd(turn=record.turn, stop_reason=record.stop_reason))
            if record.stop_reason in ("error", "aborted"):
                return _InnerOutcome(cast(RunOutcome, record.stop_reason), turns, record.stop_reason)
            continue_requested = await self._finish_turn(record)
            await self._prepare_next_turn(record)
            if record.terminated:
                return _InnerOutcome("terminated", turns, record.stop_reason)
            if record.tool_calls or self._steering or continue_requested:
                continue
            return _InnerOutcome("settled", turns, record.stop_reason)

    async def _run_turn(self, turn: int, abort: threading.Event | None) -> _TurnRecord:
        """一个 turn：注入 steering → prepareRequest → 流式响应 → 分类 → 工具 → 原子提交。"""
        self._messages.extend({"role": "user", "content": message} for message in self._steering.drain())
        request = self._request_context(turn)
        for hook in self._prepare_request_hooks:
            await hook.callback(request)
        self._message_seq += 1
        stream = self._llm.stream(
            StreamRequest(
                model=request.model,
                messages=request.messages,
                tools=request.tools or None,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            ),
            abort=abort,
        )
        assistant, stop_reason = await self._consume(f"m{self._message_seq}", stream)
        tool_calls = tuple(assistant.get("tool_calls") or ())
        observations = await self._resolve_tool_calls(tool_calls, stop_reason)
        tool_results = self._commit(assistant, observations)
        return _TurnRecord(
            turn=turn,
            stop_reason=stop_reason,
            assistant=assistant,
            tool_calls=tool_calls,
            observations=observations,
            tool_results=tool_results,
        )

    async def _consume(self, message_id: str, stream: Iterable[LLMEvent]) -> tuple[ChatMessage, StopReason]:
        """消费一条 LLM 流：发出 message_* 事件并把增量归并成 assistant 消息与终止原因。

        同步 SDK 流在 daemon 线程迭代（iterate_in_thread），事件循环保持可响应；
        每个事件后让出一次，前端消息泵有机会把已到的增量落屏。
        """
        text_parts: list[str] = []
        calls = ToolCallBuilder()
        stop_reason: StopReason | None = None
        async for event in iterate_in_thread(message_events(message_id, stream)):
            self._emit(event)
            if isinstance(event, MessageUpdate):
                if isinstance(event.delta, TextDelta):
                    text_parts.append(event.delta.text)
                elif isinstance(event.delta, ToolCallDelta):
                    calls.add(event.delta)
            elif isinstance(event, MessageEnd):
                stop_reason = event.stop_reason
            await asyncio.sleep(0)
        if stop_reason is None:
            raise ValueError(f"LLM stream for message '{message_id}' ended without Done")
        tool_calls = calls.build()
        content = "".join(text_parts)
        assistant: ChatMessage = {"role": "assistant", "content": content or (None if tool_calls else "")}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        return assistant, stop_reason

    async def _resolve_tool_calls(
        self, tool_calls: Sequence[Mapping[str, Any]], stop_reason: StopReason
    ) -> tuple[Observation, ...]:
        """按 stopReason 分类处理本轮 tool call：正常走流水线；error/aborted/length 全部判失败不执行。"""
        if not tool_calls:
            return ()
        if stop_reason in ("error", "aborted"):
            return self._fail_tool_calls(tool_calls, NOT_EXECUTED.format(reason=stop_reason))
        if stop_reason == "length":
            return self._fail_tool_calls(tool_calls, TRUNCATED)
        observations: list[Observation] = []
        for call in tool_calls:
            function = call.get("function") or {}
            observations.append(
                await self._pipeline.run(
                    ToolRequest(
                        tool_call_id=str(call.get("id") or ""),
                        name=str(function.get("name") or ""),
                        arguments=str(function.get("arguments") or ""),
                    )
                )
            )
        return tuple(observations)

    def _fail_tool_calls(self, tool_calls: Sequence[Mapping[str, Any]], reason: str) -> tuple[Observation, ...]:
        """把一批 tool call 判失败（不执行）：发出配对的 tool_execution 事件并产出 error 观察。

        arguments 保留模型发出的原始（可能截断的）内容，供 finishTurn hook 与 UI 视图诊断。
        """
        observations: list[Observation] = []
        for call in tool_calls:
            function = call.get("function") or {}
            tool_call_id = str(call.get("id") or "")
            name = str(function.get("name") or "")
            arguments = str(function.get("arguments") or "")
            self._emit(ToolExecutionStart(tool_call_id=tool_call_id, name=name, arguments=arguments))
            observation = Observation(
                tool_call_id=tool_call_id,
                name=name,
                arguments={"raw": arguments},
                content=reason,
                status="error",
                error=reason,
            )
            self._emit(ToolExecutionEnd(tool_call_id=tool_call_id, observation=observation))
            observations.append(observation)
        return tuple(observations)

    def _commit(self, assistant: ChatMessage, observations: Sequence[Observation]) -> tuple[ChatMessage, ...]:
        """原子提交一个 turn：assistant 与其全部 tool 结果一起入账，历史绝不出现未配对 tool_calls。"""
        tool_results = tuple(_tool_result_message(observation) for observation in observations)
        self._messages.append(assistant)
        self._messages.extend(tool_results)
        return tool_results

    async def _finish_turn(self, record: _TurnRecord) -> bool:
        """finishTurn 链：任一 hook 返回 "continue" 即要求再跑一轮；其余返回值显式拒绝。"""
        result = _turn_result(record)
        continue_requested = False
        for hook in self._finish_turn_hooks:
            decision: FinishDecision = await hook.callback(result)
            if decision is not None and decision != "continue":
                raise TypeError(f"finish_turn hook returned {decision!r}; expected 'continue' or None")
            continue_requested = continue_requested or decision == "continue"
        return continue_requested

    async def _prepare_next_turn(self, record: _TurnRecord) -> None:
        """prepareNextTurn 链：每个已完成 turn 的边界都执行，返回的 NextTurnUpdate 持久替换引擎状态。"""
        result = _turn_result(record)
        for hook in self._prepare_next_turn_hooks:
            context = NextTurnContext(
                turn=self._turn_seq + 1,
                result=result,
                model=self._model,
                messages=tuple(self._messages),
                tools=tuple(self._tool_schemas),
            )
            update = await hook.callback(context)
            if update is None:
                continue
            if not isinstance(update, NextTurnUpdate):
                raise TypeError(
                    f"prepare_next_turn hook returned {type(update).__name__}; expected NextTurnUpdate or None"
                )
            if update.model is not None:
                self._model = update.model
            if update.messages is not None:
                self._messages = list(update.messages)
            if update.tools is not None:
                self._tool_schemas = list(update.tools)

    def _request_context(self, turn: int) -> RequestContext:
        """本次请求的可变视图：消息是快照拷贝，prepareRequest 的注入只影响本次请求。"""
        return RequestContext(
            turn=turn,
            model=self._model,
            messages=[dict(message) for message in self._messages],
            tools=list(self._tool_schemas),
        )

    def _require_continuation_point(self) -> None:
        """显式 continuation 要求上下文可续跑：最后一条消息必须是 user 输入或 tool 结果。"""
        if not self._messages:
            raise ValueError("explicit continuation needs an existing conversation")
        if self._messages[-1].get("role") not in ("user", "tool"):
            raise ValueError("explicit continuation requires the last message to be a user or tool message")

    def _emit(self, event: AgentEvent) -> None:
        if self._sink is not None:
            self._sink.emit(event)


@dataclass(frozen=True)
class _TurnRecord:
    """一个已完成 turn 的全部产物（内部传递视图）。"""

    turn: int
    stop_reason: StopReason
    assistant: ChatMessage
    tool_calls: tuple[Mapping[str, Any], ...]
    observations: tuple[Observation, ...]
    tool_results: tuple[ChatMessage, ...]

    @property
    def terminated(self) -> bool:
        """pi 语义：一个批次的全部结果都 terminate 才请求停止。"""
        return bool(self.observations) and all(observation.terminate for observation in self.observations)


@dataclass(frozen=True)
class _InnerOutcome:
    """内层循环的一次收束：方式、完成的 turn 数与最后一次响应的终止原因。"""

    outcome: RunOutcome
    turns: int
    stop_reason: StopReason | None


def _tool_result_message(observation: Observation) -> ChatMessage:
    """Observation → 发给模型的 tool 结果消息。"""
    return {
        "role": "tool",
        "tool_call_id": observation.tool_call_id,
        "name": observation.name,
        "content": observation.content,
    }


def _turn_result(record: _TurnRecord) -> TurnResult:
    return TurnResult(turn=record.turn, message=record.assistant, observations=record.observations)

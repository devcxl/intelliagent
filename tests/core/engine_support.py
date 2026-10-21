"""引擎测试的 fake 与装配辅助：脚本化 LLM、事件收集器、工具执行记录器。

引擎测试只走声明的 seam（Spec #49 seam 1：事件流 + 返回值 + Conversation 记录），不碰私有属性。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from src.core.agent_events import AgentEvent, EventSink
from src.core.engine import Engine, tool_schemas
from src.core.tool_pipeline import HookProvider, ToolPipeline, ToolProvider
from src.core.turn_hooks import TurnHookProvider
from src.llm.stream import (
    ChatMessage,
    Done,
    LLMEvent,
    StopReason,
    StreamRequest,
    TextDelta,
    ToolCallDelta,
    Usage,
)
from src.plugins.basic_tools import ToolSpec, tool_success

BLOCK_TIMEOUT_SECONDS = 1.0
"""BlockingLLM 的最长阻塞时间：回归时测试不会永久挂住。"""

DEFAULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}


@dataclass
class ScriptedResponse:
    """一段脚本化响应：events 是流事件序列，on_start 在响应开始流出前执行（模拟运行中插话）。"""

    events: tuple[LLMEvent, ...]
    on_start: Callable[[], None] | None = None


class FakeLLM:
    """脚本化 LLM 客户端：按入队顺序应答，记录全部请求与 abort 信号（结构性满足 LLMClient）。"""

    def __init__(self) -> None:
        self.requests: list[StreamRequest] = []
        self.aborts: list[threading.Event | None] = []
        self._script: list[ScriptedResponse] = []

    def enqueue(self, *events: LLMEvent, on_start: Callable[[], None] | None = None) -> None:
        """按顺序排入一段响应脚本。"""
        self._script.append(ScriptedResponse(events=tuple(events), on_start=on_start))

    def stream(self, request: StreamRequest, *, abort: threading.Event | None = None) -> Iterator[LLMEvent]:
        self.requests.append(request)
        self.aborts.append(abort)
        if not self._script:
            yield Done(stop_reason="stop", usage=None)
            return
        step = self._script.pop(0)
        if step.on_start is not None:
            step.on_start()
        yield from step.events


class BlockingLLM(FakeLLM):
    """首个增量后阻塞的 LLM：模拟同步 SDK 等待下一块网络数据，验证事件循环不被占住。"""

    def __init__(self) -> None:
        super().__init__()
        self.first_chunk = threading.Event()
        self.release = threading.Event()

    def stream(self, request: StreamRequest, *, abort: threading.Event | None = None) -> Iterator[LLMEvent]:
        self.requests.append(request)
        self.aborts.append(abort)
        yield TextDelta(text="first")
        self.first_chunk.set()
        self.release.wait(timeout=BLOCK_TIMEOUT_SECONDS)
        yield TextDelta(text="second")
        yield Done(stop_reason="stop", usage=None)


class RecordingSink:
    """收集全部事件；on_emit 在事件发生时立即执行，供"执行前"这类现场断言使用。"""

    def __init__(self, on_emit: Callable[[AgentEvent], None] | None = None) -> None:
        self.events: list[AgentEvent] = []
        self._on_emit = on_emit

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)
        if self._on_emit is not None:
            self._on_emit(event)


def event_names(events: Sequence[AgentEvent]) -> list[str]:
    """事件类型名序列，供顺序断言。"""
    return [type(event).__name__ for event in events]


def text_events(*texts: str, stop: StopReason = "stop") -> tuple[LLMEvent, ...]:
    """纯文本响应：每个字符串一个增量，Done 收尾。"""
    return (*[TextDelta(text=text) for text in texts], Done(stop_reason=stop, usage=_usage()))


def tool_call_events(calls: Sequence[tuple[str, str, str]], *, stop: StopReason = "stop") -> tuple[LLMEvent, ...]:
    """工具调用响应：calls 是 (id, name, arguments_json) 序列，参数拆成两段增量模拟流式拼接。"""
    events: list[LLMEvent] = []
    for index, (call_id, name, arguments) in enumerate(calls):
        middle = len(arguments) // 2
        events.append(ToolCallDelta(index=index, id=call_id, name=name, arguments_delta=arguments[:middle]))
        events.append(ToolCallDelta(index=index, id=None, name=None, arguments_delta=arguments[middle:]))
    events.append(Done(stop_reason=stop, usage=_usage()))
    return tuple(events)


def make_tool(
    log: list[str],
    *,
    name: str = "rec",
    result: str | None = None,
    schema: dict[str, Any] | None = None,
) -> ToolSpec:
    """记录执行的 fake 工具：执行时向 log 追加 "execute:<name>"，默认返回成功信封。"""

    async def handler(**kwargs: Any) -> str:
        log.append(f"execute:{name}")
        return result if result is not None else tool_success(received=kwargs)

    return ToolSpec(name=name, description="test tool", parameters=schema or DEFAULT_SCHEMA, handler=handler)


def build_engine(
    llm: FakeLLM,
    *,
    tools: Sequence[ToolSpec] = (),
    turn_hooks: Sequence[TurnHookProvider] = (),
    tool_hooks: Sequence[HookProvider] = (),
    sink: EventSink | None = None,
    model: str = "fake/model",
    **options: Any,
) -> Engine:
    """不经过 PluginHost 直接装配引擎，供循环语义测试使用。"""
    tool_map: dict[str, ToolProvider] = {spec.name: spec for spec in tools}
    pipeline = ToolPipeline(tools=tool_map, hooks=tool_hooks, sink=sink)
    return Engine(
        llm,
        pipeline,
        tool_schemas(tool_map),
        model=model,
        hooks=turn_hooks,
        sink=sink,
        **options,
    )


def assert_tool_calls_paired(messages: Sequence[ChatMessage]) -> None:
    """历史一致性：每个 assistant tool_call id 都必须有配对的 tool 结果（旧引擎 P0 缺陷回归）。"""
    announced: set[str] = set()
    answered: set[str] = set()
    for message in messages:
        if message.get("role") == "tool":
            answered.add(str(message.get("tool_call_id")))
        for call in message.get("tool_calls") or []:
            announced.add(str(call.get("id")))
    unpaired = announced - answered
    assert not unpaired, f"unpaired assistant tool_calls: {sorted(unpaired)}"


def tool_arguments(path: str) -> str:
    """构造 rec 工具的合法参数 JSON 文本。"""
    return json.dumps({"path": path})


def _usage() -> Usage:
    return Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)

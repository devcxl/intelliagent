"""compaction 测试的装配辅助：消息构造、脚本化响应、Compactor 工厂（镜像 tests/core/engine_support 的定位）。"""

from __future__ import annotations

from typing import Any

from src.core.compaction import Compactor, TokenCounter
from src.llm.stream import ChatMessage, Done, LLMEvent, StopReason, TextDelta, ToolCallDelta, Usage
from src.plugins.storage import StorageStore
from tests.core.engine_support import FakeLLM


def user(text: str) -> ChatMessage:
    """user 消息。"""
    return {"role": "user", "content": text}


def assistant(text: str, *, tool_calls: list[dict[str, Any]] | None = None) -> ChatMessage:
    """assistant 消息；带 tool_calls 时 content 可为空。"""
    message: ChatMessage = {"role": "assistant", "content": text}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    return message


def tool_result(call_id: str, text: str) -> ChatMessage:
    """tool 结果消息（与其 assistant tool_call 配对）。"""
    return {"role": "tool", "tool_call_id": call_id, "name": "rec", "content": text}


def tool_call(call_id: str, arguments: str) -> dict[str, Any]:
    """模型侧 tool_call 形态。"""
    return {"id": call_id, "type": "function", "function": {"name": "rec", "arguments": arguments}}


def padding(marker: str, size: int = 400) -> str:
    """marker 打头、补齐到 size 字符的正文（size/4 即估算 token 数）。"""
    return (marker + "x" * size)[:size]


def summary_response(text: str, *, stop: StopReason = "stop") -> tuple[LLMEvent, ...]:
    """一段摘要响应：单个文本增量 + Done 收尾。"""
    return (TextDelta(text=text), Done(stop_reason=stop, usage=None))


def text_response(text: str, *, usage: Usage | None = None) -> tuple[LLMEvent, ...]:
    """一段纯文本响应，usage 可指定（阈值触发测试用真实 usage 驱动）。"""
    return (TextDelta(text=text), Done(stop_reason="stop", usage=usage))


def tool_call_response(call_id: str, name: str, arguments: str, *, usage: Usage | None = None) -> tuple[LLMEvent, ...]:
    """一段工具调用响应：参数拆两段增量模拟流式拼接。"""
    middle = len(arguments) // 2
    return (
        ToolCallDelta(index=0, id=call_id, name=name, arguments_delta=arguments[:middle]),
        ToolCallDelta(index=0, id=None, name=None, arguments_delta=arguments[middle:]),
        Done(stop_reason="stop", usage=usage),
    )


def make_compactor(
    llm: FakeLLM,
    store: StorageStore,
    *,
    counter: TokenCounter | None = None,
    context_window: int = 1_000_000,
    reserve_tokens: int = 16_384,
    keep_recent_tokens: int = 100,
    max_summary_attempts: int = 3,
    resume_entry_id: str | None = None,
    model: str = "fake/model",
) -> Compactor:
    """按测试场景装配 Compactor（参数默认值适合 400 字符/100 token 的样例消息）。"""
    return Compactor(
        llm,
        store,
        model=model,
        counter=counter or TokenCounter(),
        context_window=context_window,
        reserve_tokens=reserve_tokens,
        keep_recent_tokens=keep_recent_tokens,
        max_summary_attempts=max_summary_attempts,
        resume_entry_id=resume_entry_id,
    )

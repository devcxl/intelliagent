"""litellm 临时适配器（T0）：保留既有传输行为，作为编排层替换前的过渡实现。

T1 用原生 openai-compatible 适配器取代本模块后删除。这里的职责只有：
请求参数拼装、流 chunk 翻译、litellm/OpenAI 异常到 ProviderError 的分类。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import litellm
from litellm.exceptions import (
    APIConnectionError,
    BadGatewayError,
    InternalServerError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from openai import OpenAIError

from src.llm.errors import ProviderError
from src.llm.stream import Done, LLMEvent, StopReason, StreamRequest, TextDelta, ToolCallDelta, Usage, abort_requested

# 调用类异常：进入流（Error + Done("error")）而非同步抛出（pi 纪律）。
# 基类用 openai.OpenAIError——litellm 的全部 API 异常（BadRequest/Timeout/RateLimit...）继承它。
# 编程错误（AttributeError/TypeError 等）不属于此类，必须原样抛出。
_CALL_EXCEPTIONS: tuple[type[BaseException], ...] = (OpenAIError, TimeoutError, ConnectionError)

_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    Timeout,
    RateLimitError,
    APIConnectionError,
    ServiceUnavailableError,
    InternalServerError,
    BadGatewayError,
)

_COMPLETE_FINISH_REASONS = frozenset({"stop", "tool_calls", "function_call"})


class LitellmAdapter:
    """把 litellm 的一次流式调用翻译为统一 LLMEvent 序列。"""

    def stream(
        self, request: StreamRequest, abort: threading.Event | None = None, *, timeout: float
    ) -> Iterator[LLMEvent]:
        """产出一次模型响应的流式事件序列，每条流以恰好一个 Done 结束。"""
        try:
            stream = self._open_stream(request, timeout)
        except _CALL_EXCEPTIONS as exc:
            raise _provider_error(exc) from exc
        done_yielded = False
        try:
            finish_reason: str | None = None
            usage: Usage | None = None
            for chunk in stream:
                if abort_requested(abort):
                    # abort 时已消耗的 token 仍随 Done 落账（编排层从 Done 记账）。
                    done_yielded = True
                    yield Done(stop_reason="aborted", usage=usage)
                    return
                usage = _extract_usage(chunk) or usage
                choice = _first_choice(chunk)
                if choice is not None:
                    delta = _field(choice, "delta")
                    text = _field(delta, "content")
                    if text:
                        yield TextDelta(text=text)
                    for raw_tool_call in _field(delta, "tool_calls") or []:
                        tool_event = _tool_call_delta(raw_tool_call)
                        if tool_event is not None:
                            yield tool_event
                    chunk_finish = _field(choice, "finish_reason")
                    if chunk_finish is not None:
                        finish_reason = chunk_finish
            done = Done(stop_reason=_map_stop_reason(finish_reason), usage=usage)
            done_yielded = True
            yield done
        except _CALL_EXCEPTIONS as exc:
            raise _provider_error(exc) from exc
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except _CALL_EXCEPTIONS as exc:
                    # close 失败仅在 Done 尚未产出时才可行动（抛给重试/错误进流）；
                    # Done 之后的清理异常不得二次产出事件破坏"恰好一个 Done"协议。
                    if not done_yielded:
                        raise _provider_error(exc) from exc
                except Exception:
                    if not done_yielded:
                        raise

    def _open_stream(self, request: StreamRequest, timeout: float) -> Any:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "timeout": timeout,
        }
        if request.tools is not None:
            kwargs["tools"] = request.tools
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        # litellm 1.106 只要 tools 非空就导入其 proxy MCP 模块，该模块要求 mcp>=2.2；
        # 本项目锁定的 mcp 1.x 没有 CacheableResult，运行期 ImportError 会让所有工具调用不可用。
        # 本项目不使用 litellm 的 MCP 网关（MCP 由内置插件自管），故跳过该分支。
        # T1 用原生适配器取代 litellm 后随本模块一起删除。
        kwargs["_skip_mcp_handler"] = True
        return litellm.completion(**kwargs)


def _provider_error(exc: Exception) -> ProviderError:
    return ProviderError(f"{type(exc).__name__}: {exc}", retryable=isinstance(exc, _RETRYABLE_EXCEPTIONS))


def _field(obj: Any, name: str) -> Any:
    """litellm 跨 provider 的 chunk 既可能是对象也可能是 dict，统一取字段。"""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _first_choice(chunk: Any) -> Any:
    choices = _field(chunk, "choices") or []
    return choices[0] if choices else None


def _extract_usage(chunk: Any) -> Usage | None:
    """从 chunk 提取 usage（provider 真实值）；usage-only chunk 或收尾 chunk 都可能携带。"""
    raw = _field(chunk, "usage")
    if raw is None:
        hidden = _field(chunk, "hidden_params")
        raw = _field(hidden, "usage") if hidden is not None else None
    if raw is None:
        return None
    prompt_tokens = _field(raw, "prompt_tokens") or 0
    completion_tokens = _field(raw, "completion_tokens") or 0
    if prompt_tokens == 0 and completion_tokens == 0:
        return None
    total_tokens = _field(raw, "total_tokens")
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens if total_tokens is not None else prompt_tokens + completion_tokens,
    )


def _tool_call_delta(raw: Any) -> ToolCallDelta | None:
    function = _field(raw, "function")
    tool_id = _field(raw, "id")
    name = _field(function, "name")
    arguments = _field(function, "arguments") or ""
    if tool_id is None and name is None and not arguments:
        return None
    return ToolCallDelta(index=_field(raw, "index") or 0, id=tool_id, name=name, arguments_delta=arguments)


def _map_stop_reason(finish_reason: str | None) -> StopReason:
    """映射 finish_reason 为统一流协议的 StopReason。

    只有明确的完整结束（stop/tool_calls/function_call）归 "stop"；截断（length/max_tokens）
    与未知/缺失 finish_reason（如 content_filter 过滤、连接异常收尾）一律归 "length"——
    这类响应可能携带残缺 tool call，按 US22 必须判失败让模型重发，不得执行残缺参数。
    """
    if finish_reason in _COMPLETE_FINISH_REASONS:
        return "stop"
    return "length"

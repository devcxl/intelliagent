"""OpenAI Chat Completions 适配器（type: openai-compatible）。

只负责请求投影、流事件翻译与错误分类；重试、超时、abort 与 usage 账本在 ProviderClient。
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from src.llm.errors import ProviderError
from src.llm.provider_registry import ModelTarget
from src.llm.stream import (
    Done,
    LLMEvent,
    StopReason,
    StreamRequest,
    TextDelta,
    ToolCallDelta,
    Usage,
    abort_requested,
)

_CALL_EXCEPTIONS: tuple[type[BaseException], ...] = (OpenAIError, TimeoutError, ConnectionError)
_COMPLETE_FINISH_REASONS = frozenset({"stop", "tool_calls", "function_call"})


class OpenAIChatAdapter:
    """Chat Completions 流式适配器；客户端工厂可注入，测试不触网。"""

    def __init__(self, client_factory: Callable[[ModelTarget, float], Any] | None = None) -> None:
        self._client_factory = client_factory if client_factory is not None else _build_client

    def stream(
        self, target: ModelTarget, request: StreamRequest, abort: threading.Event | None = None, *, timeout: float
    ) -> Iterator[LLMEvent]:
        """产出一次 Chat Completions 的流式事件序列，每条流以恰好一个 Done 结束。"""
        client: Any = None
        try:
            client = self._client_factory(target, timeout)
            stream = client.chat.completions.create(**self._request_kwargs(target, request))
        except _CALL_EXCEPTIONS as exc:
            _close(client)
            raise _provider_error(exc) from exc

        done_yielded = False
        try:
            finish_reason: str | None = None
            usage: Usage | None = None
            for chunk in stream:
                if abort_requested(abort):
                    done_yielded = True
                    yield Done(stop_reason="aborted", usage=usage)
                    return
                usage = _extract_usage(chunk) or usage
                choice = _first_choice(chunk)
                if choice is not None:
                    delta = getattr(choice, "delta", None)
                    text = getattr(delta, "content", None)
                    if text:
                        yield TextDelta(text=text)
                    for raw_tool_call in getattr(delta, "tool_calls", None) or ():
                        tool_event = _tool_call_delta(raw_tool_call)
                        if tool_event is not None:
                            yield tool_event
                    chunk_finish = getattr(choice, "finish_reason", None)
                    if chunk_finish is not None:
                        finish_reason = chunk_finish
            done = Done(stop_reason=_map_stop_reason(finish_reason), usage=usage)
            done_yielded = True
            yield done
        except _CALL_EXCEPTIONS as exc:
            raise _provider_error(exc) from exc
        finally:
            try:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
            except _CALL_EXCEPTIONS as exc:
                if not done_yielded:
                    raise _provider_error(exc) from exc
            except Exception:
                if not done_yielded:
                    raise
            finally:
                _close(client)

    def _request_kwargs(self, target: ModelTarget, request: StreamRequest) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": target.wire_model,
            "messages": request.messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if target.supports_tools and request.tools is not None:
            kwargs["tools"] = request.tools
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        max_tokens = request.max_tokens if request.max_tokens is not None else target.max_output_tokens
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return kwargs


def _build_client(target: ModelTarget, timeout: float) -> OpenAI:
    return OpenAI(
        api_key=target.api_key or "not-needed",
        base_url=target.api_base,
        timeout=timeout,
        max_retries=0,
    )


def _close(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            # 清理异常不得覆盖已分类的调用错误。
            pass


def _provider_error(exc: Exception) -> ProviderError:
    return ProviderError(f"{type(exc).__name__}: {exc}", retryable=_is_retryable(exc))


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (ConnectionError, TimeoutError, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError),
    ):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _first_choice(chunk: Any) -> Any:
    choices = getattr(chunk, "choices", None) or ()
    return choices[0] if choices else None


def _extract_usage(chunk: Any) -> Usage | None:
    raw = getattr(chunk, "usage", None)
    if raw is None:
        return None
    prompt_tokens = getattr(raw, "prompt_tokens", 0) or 0
    completion_tokens = getattr(raw, "completion_tokens", 0) or 0
    if prompt_tokens == 0 and completion_tokens == 0:
        return None
    total_tokens = getattr(raw, "total_tokens", None)
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens if total_tokens is not None else prompt_tokens + completion_tokens,
    )


def _tool_call_delta(raw: Any) -> ToolCallDelta | None:
    function = getattr(raw, "function", None)
    tool_id = getattr(raw, "id", None)
    name = getattr(function, "name", None)
    arguments = getattr(function, "arguments", None) or ""
    if tool_id is None and name is None and not arguments:
        return None
    return ToolCallDelta(
        index=getattr(raw, "index", 0) or 0,
        id=tool_id,
        name=name,
        arguments_delta=arguments,
    )


def _map_stop_reason(finish_reason: str | None) -> StopReason:
    """只有明确的完整结束归 stop；截断与未知终止归 length（不执行残缺工具参数）。"""
    return "stop" if finish_reason in _COMPLETE_FINISH_REASONS else "length"

"""litellm 统一模型接入：消费 litellm 流式接口，产出统一流协议事件（src/llm/stream.py）。

provider 差异由 litellm 的 model 字符串（如 "openai/gpt-4o"）收敛，本模块不做 provider 分类。
照搬 pi 的两条纪律（docs/pi-engine-principles.md §7）：错误进流而非同步抛出、usage 逐响应落账。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
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

from src.llm.stream import Done, Error, LLMEvent, StopReason, StreamRequest, TextDelta, ToolCallDelta, Usage

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

_TRUNCATED_FINISH_REASONS = frozenset({"length", "max_tokens"})


class LiteLLMClient:
    """基于 litellm 的 LLMClient 实现：token 级流式、usage 落账、超时重试。

    Attributes:
        usage_log: 逐响应落账的 token 用量（每个正常完成的响应一条）。
    """

    def __init__(
        self,
        *,
        request_timeout: float = 60.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """初始化客户端。

        Args:
            request_timeout: 单次模型调用的超时（秒），透传给 litellm。
            max_retries: 瞬时错误的最大重试次数（总尝试次数 = max_retries + 1，不做无限重试）。
            backoff_base_seconds: 退避基数（秒），第 n 次重试前等待 backoff_base * 2**n。
            sleep: 退避等待函数，测试中注入以记录延迟而不真正等待。
        """
        self._request_timeout = request_timeout
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
        self.usage_log: list[Usage] = []

    def stream(self, request: StreamRequest, *, abort: threading.Event | None = None) -> Iterator[LLMEvent]:
        """产出一次模型响应的流式事件序列，每条流以恰好一个 Done 结束。"""
        yield from self._stream_with_retries(request, abort)

    def _stream_with_retries(self, request: StreamRequest, abort: threading.Event | None) -> Iterator[LLMEvent]:
        failed_attempts = 0
        while True:
            if _is_aborted(abort):
                yield Done(stop_reason="aborted", usage=None)
                return
            emitted = False
            try:
                for event in self._attempt(request, abort):
                    emitted = True
                    yield event
                return
            except Exception as exc:
                # 已产出增量的流不重试：重放会把增量重复发给消费者；错误进流而非同步抛出。
                if not emitted and failed_attempts < self._max_retries and isinstance(exc, _RETRYABLE_EXCEPTIONS):
                    self._sleep(self._backoff_base_seconds * (2**failed_attempts))
                    failed_attempts += 1
                    continue
                yield Error(message=f"{type(exc).__name__}: {exc}")
                yield Done(stop_reason="error", usage=None)
                return

    def _attempt(self, request: StreamRequest, abort: threading.Event | None) -> Iterator[LLMEvent]:
        stream = self._open_stream(request)
        try:
            finish_reason: str | None = None
            usage: Usage | None = None
            for chunk in stream:
                if _is_aborted(abort):
                    yield Done(stop_reason="aborted", usage=None)
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
            if usage is not None:
                self.usage_log.append(usage)
            yield done
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()

    def _open_stream(self, request: StreamRequest) -> Any:
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            "timeout": self._request_timeout,
        }
        if request.tools is not None:
            kwargs["tools"] = request.tools
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        return litellm.completion(**kwargs)


def _is_aborted(abort: threading.Event | None) -> bool:
    return abort is not None and abort.is_set()


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
    return "length" if finish_reason in _TRUNCATED_FINISH_REASONS else "stop"

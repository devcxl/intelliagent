"""Anthropic Messages 适配器（type: anthropic）。

只负责请求投影、流事件翻译与错误分类；重试、超时、abort 与 usage 账本在 ProviderClient。
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from typing import Any

from anthropic import (
    Anthropic,
    AnthropicError,
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    OverloadedError,
    RateLimitError,
    RetryableError,
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

_CALL_EXCEPTIONS: tuple[type[BaseException], ...] = (AnthropicError, TimeoutError, ConnectionError)
_COMPLETE_STOP_REASONS = frozenset({"end_turn", "tool_use", "stop_sequence", "refusal"})
_DEFAULT_MAX_TOKENS = 4096


class AnthropicMessagesAdapter:
    """Messages 流式适配器；客户端工厂可注入，测试不触网。"""

    def __init__(self, client_factory: Callable[[ModelTarget, float], Any] | None = None) -> None:
        self._client_factory = client_factory if client_factory is not None else _build_client

    def stream(
        self, target: ModelTarget, request: StreamRequest, abort: threading.Event | None = None, *, timeout: float
    ) -> Iterator[LLMEvent]:
        """产出一次 Messages 的流式事件序列，每条流以恰好一个 Done 结束。"""
        client: Any = None
        try:
            client = self._client_factory(target, timeout)
            stream = client.messages.create(**self._request_kwargs(target, request))
        except _CALL_EXCEPTIONS as exc:
            _close(client)
            raise _provider_error(exc) from exc

        done_yielded = False
        try:
            input_tokens = 0
            output_tokens = 0
            finish_reason: str | None = None
            tool_blocks: dict[int, tuple[str | None, str | None]] = {}
            for event in stream:
                if abort_requested(abort):
                    done_yielded = True
                    yield Done(stop_reason="aborted", usage=_usage(input_tokens, output_tokens))
                    return
                event_type = getattr(event, "type", None)
                if event_type == "message_start":
                    usage = getattr(getattr(event, "message", None), "usage", None)
                    input_tokens = getattr(usage, "input_tokens", 0) or 0
                    output_tokens = getattr(usage, "output_tokens", 0) or 0
                elif event_type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if getattr(block, "type", None) == "tool_use":
                        tool_blocks[event.index] = (getattr(block, "id", None), getattr(block, "name", None))
                        yield ToolCallDelta(event.index, getattr(block, "id", None), getattr(block, "name", None), "")
                elif event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    delta_type = getattr(delta, "type", None)
                    if delta_type == "text_delta":
                        text = getattr(delta, "text", None)
                        if text:
                            yield TextDelta(text=text)
                    elif delta_type == "input_json_delta":
                        tool_id, name = tool_blocks.get(event.index, (None, None))
                        yield ToolCallDelta(event.index, tool_id, name, getattr(delta, "partial_json", "") or "")
                elif event_type == "message_delta":
                    finish_reason = getattr(getattr(event, "delta", None), "stop_reason", None)
                    usage = getattr(event, "usage", None)
                    output_tokens = getattr(usage, "output_tokens", output_tokens) or output_tokens
                elif event_type == "error":
                    error = getattr(event, "error", None)
                    raise ProviderError(
                        f"{getattr(error, 'type', 'error')}: {getattr(error, 'message', '')}",
                        retryable=getattr(error, "type", "") in {"overloaded_error", "api_error"},
                    )
            done = Done(stop_reason=_map_stop_reason(finish_reason), usage=_usage(input_tokens, output_tokens))
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
        system, messages = _build_messages(request)
        max_tokens = request.max_tokens if request.max_tokens is not None else target.max_output_tokens
        kwargs: dict[str, Any] = {
            "model": target.wire_model,
            "messages": messages,
            "max_tokens": max_tokens or _DEFAULT_MAX_TOKENS,
            "stream": True,
        }
        if system:
            kwargs["system"] = system
        if target.supports_tools and request.tools is not None:
            kwargs["tools"] = _build_tools(request.tools)
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        return kwargs


def _build_messages(request: StreamRequest) -> tuple[str, list[dict[str, Any]]]:
    """内部 OpenAI chat 形状 → Anthropic Messages：system 提升、tool_use/tool_result 投影。"""
    system_parts: list[str] = []
    messages: list[dict[str, Any]] = []
    for message in request.messages:
        role = message.get("role")
        if role == "system":
            system_parts.append(str(message.get("content") or ""))
            continue
        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            text = message.get("content")
            if text:
                blocks.append({"type": "text", "text": str(text)})
            for call in message.get("tool_calls") or ():
                function = call.get("function") or {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or "",
                        "name": function.get("name") or "",
                        "input": _parse_arguments(function.get("arguments")),
                    }
                )
            messages.append({"role": "assistant", "content": blocks or ""})
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id") or "",
                "content": str(message.get("content") or ""),
            }
            if messages and messages[-1]["role"] == "user" and _is_tool_result_message(messages[-1]):
                messages[-1]["content"].append(block)
            else:
                messages.append({"role": "user", "content": [block]})
            continue
        messages.append({"role": "user", "content": str(message.get("content") or "")})
    return "\n\n".join(part for part in system_parts if part), messages


def _is_tool_result_message(message: dict[str, Any]) -> bool:
    content = message.get("content")
    return isinstance(content, list) and all(block.get("type") == "tool_result" for block in content)


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(str(raw))
    if not isinstance(parsed, dict):
        raise ValueError("tool call arguments must decode to a JSON object")
    return parsed


def _build_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": (tool.get("function") or {}).get("name") or "",
            "description": (tool.get("function") or {}).get("description") or "",
            "input_schema": (tool.get("function") or {}).get("parameters") or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


def _usage(input_tokens: int, output_tokens: int) -> Usage | None:
    if input_tokens == 0 and output_tokens == 0:
        return None
    return Usage(prompt_tokens=input_tokens, completion_tokens=output_tokens, total_tokens=input_tokens + output_tokens)


def _build_client(target: ModelTarget, timeout: float) -> Anthropic:
    return Anthropic(
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
            pass


def _provider_error(exc: Exception) -> ProviderError:
    return ProviderError(f"{type(exc).__name__}: {exc}", retryable=_is_retryable(exc))


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
            InternalServerError,
            OverloadedError,
            RetryableError,
        ),
    ):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _map_stop_reason(stop_reason: str | None) -> StopReason:
    return "stop" if stop_reason in _COMPLETE_STOP_REASONS else "length"

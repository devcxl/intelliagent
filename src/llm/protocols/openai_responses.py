"""OpenAI Responses 适配器（type: openai）。

只负责请求投影、流事件翻译与错误分类；重试、超时、abort 与 usage 账本在 ProviderClient。
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any

from src.llm.errors import ProviderError
from src.llm.protocols.openai_common import CALL_EXCEPTIONS, build_client, close_quietly, provider_error
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


class OpenAIResponsesAdapter:
    """Responses 流式适配器；客户端工厂可注入，测试不触网。"""

    def __init__(self, client_factory: Callable[[ModelTarget, float], Any] | None = None) -> None:
        self._client_factory = client_factory if client_factory is not None else build_client

    def stream(
        self, target: ModelTarget, request: StreamRequest, abort: threading.Event | None = None, *, timeout: float
    ) -> Iterator[LLMEvent]:
        """产出一次 Responses 的流式事件序列，每条流以恰好一个 Done 结束。"""
        client: Any = None
        try:
            client = self._client_factory(target, timeout)
            stream = client.responses.create(**self._request_kwargs(target, request))
        except CALL_EXCEPTIONS as exc:
            close_quietly(client)
            raise provider_error(exc) from exc

        done_yielded = False
        try:
            usage: Usage | None = None
            finish_reason: str | None = None
            tool_items: dict[str, tuple[str | None, str | None, int]] = {}
            for event in stream:
                if abort_requested(abort):
                    done_yielded = True
                    yield Done(stop_reason="aborted", usage=usage)
                    return
                event_type = getattr(event, "type", None)
                if event_type == "response.output_text.delta":
                    text = getattr(event, "delta", None)
                    if text:
                        yield TextDelta(text=text)
                elif event_type == "response.output_item.added":
                    item = getattr(event, "item", None)
                    if getattr(item, "type", None) == "function_call":
                        call_id = getattr(item, "call_id", None)
                        name = getattr(item, "name", None)
                        index = getattr(event, "output_index", 0) or 0
                        item_id = getattr(item, "id", None)
                        if item_id is not None:
                            tool_items[item_id] = (call_id, name, index)
                        yield ToolCallDelta(index, call_id, name, "")
                elif event_type == "response.function_call_arguments.delta":
                    item_id = getattr(event, "item_id", None)
                    call_id, name, index = tool_items.get(item_id, (None, None, getattr(event, "output_index", 0) or 0))
                    yield ToolCallDelta(index, call_id, name, getattr(event, "delta", "") or "")
                elif event_type in ("response.completed", "response.incomplete"):
                    response = getattr(event, "response", None)
                    usage = _extract_usage(getattr(response, "usage", None)) or usage
                    finish_reason = "completed" if getattr(response, "status", None) == "completed" else "incomplete"
                elif event_type in ("response.failed", "error"):
                    error = getattr(event, "error", None)
                    if error is None:
                        error = getattr(getattr(event, "response", None), "error", None)
                    message = getattr(error, "message", None) or getattr(event, "message", None) or "provider error"
                    raise ProviderError(str(message), retryable=False)
            done = Done(stop_reason=_map_stop_reason(finish_reason), usage=usage)
            done_yielded = True
            yield done
        except CALL_EXCEPTIONS as exc:
            raise provider_error(exc) from exc
        finally:
            try:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
            except CALL_EXCEPTIONS as exc:
                if not done_yielded:
                    raise provider_error(exc) from exc
            except Exception:
                if not done_yielded:
                    raise
            finally:
                close_quietly(client)

    def _request_kwargs(self, target: ModelTarget, request: StreamRequest) -> dict[str, Any]:
        instructions, input_items = _build_input(request)
        kwargs: dict[str, Any] = {
            "model": target.wire_model,
            "input": input_items,
            "stream": True,
        }
        if instructions:
            kwargs["instructions"] = instructions
        if target.supports_tools and request.tools is not None:
            kwargs["tools"] = _build_tools(request.tools)
        max_output_tokens = request.max_tokens if request.max_tokens is not None else target.max_output_tokens
        if max_output_tokens is not None:
            kwargs["max_output_tokens"] = max_output_tokens
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        return kwargs


def _build_input(request: StreamRequest) -> tuple[str, list[dict[str, Any]]]:
    """内部 OpenAI chat 形状 → Responses input：system 提升、function_call/output item 投影。"""
    instructions: list[str] = []
    items: list[dict[str, Any]] = []
    for message in request.messages:
        role = message.get("role")
        if role == "system":
            instructions.append(str(message.get("content") or ""))
            continue
        if role == "assistant":
            content = message.get("content")
            if content:
                items.append({"role": "assistant", "content": str(content)})
            for call in message.get("tool_calls") or ():
                function = call.get("function") or {}
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.get("id") or "",
                        "name": function.get("name") or "",
                        "arguments": function.get("arguments") or "{}",
                    }
                )
            continue
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id") or "",
                    "output": str(message.get("content") or ""),
                }
            )
            continue
        items.append({"role": "user", "content": str(message.get("content") or "")})
    return "\n\n".join(part for part in instructions if part), items


def _build_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": (tool.get("function") or {}).get("name") or "",
            "description": (tool.get("function") or {}).get("description") or "",
            "parameters": (tool.get("function") or {}).get("parameters") or {"type": "object", "properties": {}},
        }
        for tool in tools
    ]


def _extract_usage(raw: Any) -> Usage | None:
    if raw is None:
        return None
    prompt_tokens = getattr(raw, "input_tokens", 0) or 0
    completion_tokens = getattr(raw, "output_tokens", 0) or 0
    if prompt_tokens == 0 and completion_tokens == 0:
        return None
    total_tokens = getattr(raw, "total_tokens", None)
    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens if total_tokens is not None else prompt_tokens + completion_tokens,
    )


def _map_stop_reason(finish_reason: str | None) -> StopReason:
    return "stop" if finish_reason == "completed" else "length"

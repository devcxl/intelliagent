"""OpenAI SDK 适配器共享件：客户端构造、错误分类与安静关闭（Chat / Responses 共用）。"""

from __future__ import annotations

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

CALL_EXCEPTIONS: tuple[type[BaseException], ...] = (OpenAIError, TimeoutError, ConnectionError)


def build_client(target: ModelTarget, timeout: float) -> OpenAI:
    # OpenAI SDK 必须拿到非空 api_key；openai-compatible 无密钥时用占位值，
    # 端点应忽略 Authorization（本地 vLLM/Ollama 等）。
    return OpenAI(
        api_key=target.api_key or "not-needed",
        base_url=target.api_base,
        timeout=timeout,
        max_retries=0,
    )


def close_quietly(client: Any) -> None:
    close = getattr(client, "close", None)
    if callable(close):
        try:
            close()
        except Exception:
            pass


def provider_error(exc: Exception) -> ProviderError:
    return ProviderError(f"{type(exc).__name__}: {exc}", retryable=is_retryable(exc))


def is_retryable(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (ConnectionError, TimeoutError, APIConnectionError, APITimeoutError, RateLimitError, InternalServerError),
    ):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500

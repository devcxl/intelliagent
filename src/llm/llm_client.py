#!/usr/bin/env python3
"""
LLM 客户端模块
封装 OpenAI API 调用，支持原生 function calling。
"""
import asyncio
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI

from src.utils.logger import logger


@dataclass(frozen=True)
class LLMResponse:
    content: str | None
    tool_calls: list[Any]
    usage: Any = None


class LLMClient:
    """OpenAI LLM 客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_API_BASE")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY，请设置环境变量或传入参数")

        self.model = model
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        try:
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens:
                kwargs["max_tokens"] = max_tokens
            if response_format:
                kwargs["response_format"] = response_format
            if tools:
                kwargs["tools"] = tools

            logger.debug(
                f"LLMClient - 调用开始 | model={self.model} "
                f"msg_count={len(messages)} tool_count={len(tools) if tools else 0}"
            )

            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            usage = response.usage
            tool_calls = getattr(message, "tool_calls", None) or []
            logger.debug(
                f"LLMClient - 调用成功 | "
                f"prompt_tokens={getattr(usage, 'prompt_tokens', 'N/A') if usage else 'N/A'} "
                f"completion_tokens={getattr(usage, 'completion_tokens', 'N/A') if usage else 'N/A'} "
                f"total_tokens={getattr(usage, 'total_tokens', 'N/A') if usage else 'N/A'} "
                f"has_tool_calls={bool(tool_calls)}"
            )
            return LLMResponse(
                content=message.content,
                tool_calls=tool_calls,
                usage=usage,
            )

        except Exception as e:
            logger.error(f"LLM 调用失败 | error={e}")
            raise

    async def chat_async(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> LLMResponse:
        return await asyncio.to_thread(
            self.chat,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            tools=tools,
        )


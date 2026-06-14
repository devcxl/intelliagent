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
    """LLM 调用响应，封装 OpenAI Chat Completion 的返回结果。

    Attributes:
        content: 模型返回的文本内容，无文本时可为 None。
        tool_calls: 模型请求的 function call 列表。
        usage: token 用量信息（prompt_tokens、completion_tokens、total_tokens）。
    """

    content: str | None  # 模型返回的文本内容，无文本时可为 None
    tool_calls: list[Any]  # 模型请求的 function call 列表
    usage: Any = None  # token 用量信息（prompt_tokens、completion_tokens、total_tokens）


class LLMClient:
    """OpenAI LLM 客户端，封装 Chat Completion API 调用。

    支持同步和异步两种调用方式，异步调用通过 asyncio.to_thread 委托给同步方法。
    """

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o-mini"):
        """初始化 LLM 客户端。

        Args:
            api_key: OpenAI API Key，未提供时从环境变量 OPENAI_API_KEY 读取。
            base_url: API 基础 URL，未提供时从环境变量 OPENAI_API_BASE 读取。
            model: 模型名称，默认 "gpt-4o-mini"。

        Raises:
            ValueError: api_key 和环境变量 OPENAI_API_KEY 均为空时抛出。
        """
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
        """同步调用 Chat Completion API。

        Args:
            messages: 消息列表，每条消息包含 role 和 content 字段。
            temperature: 采样温度，默认 0.7。
            max_tokens: 最大生成 token 数，None 表示不限制。
            response_format: 响应格式约束（如 {"type": "json_object"}）。
            tools: function calling 工具定义列表。

        Returns:
            LLMResponse 对象，包含 content、tool_calls 和 usage。

        Raises:
            Exception: API 调用失败时抛出原始异常。
        """
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
        """异步调用 Chat Completion API。

        通过 asyncio.to_thread 将同步 chat 方法委托到线程池执行，
        避免阻塞事件循环。

        Args:
            messages: 消息列表，每条消息包含 role 和 content 字段。
            temperature: 采样温度，默认 0.7。
            max_tokens: 最大生成 token 数，None 表示不限制。
            response_format: 响应格式约束（如 {"type": "json_object"}）。
            tools: function calling 工具定义列表。

        Returns:
            LLMResponse 对象，包含 content、tool_calls 和 usage。
        """
        return await asyncio.to_thread(
            self.chat,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            tools=tools,
        )

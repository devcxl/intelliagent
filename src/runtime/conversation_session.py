"""ConversationSession — 常驻内存的会话上下文。

核心设计：
  DB 只在首次加载时查询，后续轮次完全在内存中维护。
  ReactEngine 跨轮复用，不重建。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator

from src.core.react_engine import ReactEngine
from src.runtime.conversation_service import ConversationService
from src.runtime.engine_factory import EngineFactory


class ConversationSession:
    """单次对话的内存态表示，跨轮复用 ReactEngine 和消息列表。

    Attributes:
        conversation_id: 当前会话 ID
        tool_state:      工具可选的跨轮状态存储
    """

    def __init__(
        self,
        conversation_id: str,
        engine_factory: EngineFactory,
        conversation_service: ConversationService,
    ) -> None:
        self.conversation_id = conversation_id
        self._engine_factory = engine_factory
        self._conversation_service = conversation_service
        self._engine: ReactEngine | None = None
        self._engine_lock = asyncio.Lock()
        self.tool_state: dict[str, Any] = {}

    async def _ensure_engine(self) -> ReactEngine:
        """懒创建 ReactEngine，首次调用时从 DB 加载历史并注入。

        双重检查锁保护初始化路径，确保并发调用下只创建一次引擎。
        """
        # 快速路径：引擎已初始化，直接复用
        if self._engine is not None:
            return self._engine

        # 慢速路径：加锁后二次检查，避免 await 点上的竞态
        async with self._engine_lock:
            if self._engine is not None:
                return self._engine

            # 仅在首次：从 DB 加载全量历史，创建引擎并注入上下文
            raw_messages = await self._conversation_service.load_history_messages()
            self._engine = self._engine_factory.create(
                compact_callback=self._conversation_service.compact_messages,
            )
            self._engine.load_history(raw_messages)
            return self._engine

    async def run_turn(self, task: str) -> AsyncGenerator[dict[str, Any], None]:
        """执行一轮对话。

        流程：
          1. 懒创建/复用 ReactEngine
          2. 持久化用户消息
          3. 运行引擎迭代（复用现有内存上下文）
          4. 边运行边持久化 assistant/tool 消息

        Args:
            task: 用户输入

        Yields:
            引擎事件流（thought/action/observation/answer）
        """
        # 复用或首次创建 engine（DB 仅在此处查询一次）
        engine = await self._ensure_engine()
        # 用户消息即时落库，保证崩溃不丢
        await self._conversation_service.save_message("user", task)

        assistant_content = ""
        # engine.iter_steps 使用 reset_state=False，保留历史上下文
        async for event in engine.iter_steps(task, reset_state=False):
            # thought：LLM 返回文本+工具调用，含 tool_calls 才需持久化
            if event["type"] == "thought":
                tc = event["data"].get("tool_calls")
                if tc:
                    await self._conversation_service.save_message(
                        "assistant",
                        event["data"].get("content", ""),
                        tool_calls=json.dumps(tc, ensure_ascii=False),
                    )

            # observation：工具执行结果，关联到对应 tool_call
            elif event["type"] == "observation":
                d = event["data"]
                await self._conversation_service.save_message(
                    "tool",
                    d.get("result", ""),
                    tool_call_id=d.get("tool_call_id", ""),
                    tool_name=d.get("tool_name", ""),
                    tool_args=json.dumps(d.get("tool_args", {}), ensure_ascii=False),
                )

            # answer：最终回复，无 tool_calls 时 LLM 直接返回
            elif event["type"] == "answer":
                assistant_content = event["data"]["answer"]

            yield event

        # 最终答案在事件流结束后统一落库
        if assistant_content:
            await self._conversation_service.save_message("assistant", assistant_content)


__all__ = ["ConversationSession"]

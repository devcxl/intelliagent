#!/usr/bin/env python3
"""共享运行时装配。"""

from __future__ import annotations

from functools import lru_cache

from src.agent.react_engine import ReactEngine
from src.config import get_settings
from src.llm.llm_client import LLMClient
from src.memory.context import ContextManager
from src.memory.memory import Memory
from src.tools.tool_registry import ToolRegistry
from utils.logger import logger


class AgentRuntime:
    """共享重对象与任务级工厂。"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._default_llm_client: LLMClient | None = None

    def get_llm_client(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> LLMClient:
        """获取默认或覆盖后的 LLM 客户端。"""
        resolved_api_key = api_key or self.settings.OPENAI_API_KEY or None
        resolved_model = model or self.settings.OPENAI_MODEL
        resolved_base_url = (
            base_url if base_url is not None else self.settings.OPENAI_API_BASE
        )

        use_default_client = (
            api_key is None
            and model in {None, self.settings.OPENAI_MODEL}
            and base_url is None
        )

        if use_default_client:
            if self._default_llm_client is None:
                logger.info("初始化共享 LLM 客户端...")
                self._default_llm_client = LLMClient(
                    api_key=resolved_api_key,
                    base_url=resolved_base_url,
                    model=resolved_model,
                )
            return self._default_llm_client

        return LLMClient(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            model=resolved_model,
        )

    def create_tool_registry(self) -> ToolRegistry:
        """创建任务级工具注册中心。"""
        return ToolRegistry()

    def create_memory(self) -> Memory:
        """创建任务级 Memory。"""
        return Memory(experience_file=self.settings.EXPERIENCE_FILE)

    def create_context(self) -> ContextManager:
        """创建任务级 ContextManager。"""
        return ContextManager()

    def create_engine(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
    ) -> ReactEngine:
        """创建任务级 ReAct 引擎。"""
        return ReactEngine(
            llm_client=self.get_llm_client(api_key=api_key, model=model),
            tools=self.create_tool_registry(),
            memory=self.create_memory(),
            context=self.create_context(),
            max_iterations=max_iterations or self.settings.MAX_PDCA_CYCLES,
        )

    def warm_up(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        """预热共享运行时。"""
        self.get_llm_client(api_key=api_key, model=model)
        self.create_tool_registry()


@lru_cache(maxsize=1)
def get_runtime() -> AgentRuntime:
    """获取共享 runtime 单例。"""
    return AgentRuntime()


def clear_runtime_cache() -> None:
    """测试场景下清理 runtime 缓存。"""
    get_runtime.cache_clear()

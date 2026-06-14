#!/usr/bin/env python3
"""AgentRuntime — 管理 LLM 客户端和引擎的创建与复用。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from src.config.unified_config import UnifiedConfig
from src.core.react_engine import ReactEngine
from src.types.permission import (
    LLMClientProtocol,
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)


class AgentRuntime:
    """Agent 运行时 — 单例管理 LLM 客户端，每次创建独立 ReactEngine。

    通过 UnifiedConfig 构造。未传入 config 时自动从 intelliagent.json 加载。
    """

    def __init__(
        self,
        config: UnifiedConfig | None = None,
        *,
        llm_client_factory: Callable[[], LLMClientProtocol] | None = None,
        permission_engine_factory: Callable[[], PermissionEngineProtocol] | None = None,
        permission_callback_factory: Callable[[], PermissionCallbackProtocol] | None = None,
    ) -> None:
        self._config = config or UnifiedConfig.load()
        self._llm_client_factory = llm_client_factory or self._default_llm_client_factory
        self._permission_engine_factory = permission_engine_factory or self._default_permission_engine_factory
        self._permission_callback_factory = permission_callback_factory or self._default_permission_callback_factory
        self._llm_client: LLMClientProtocol | None = None

    # ------------------------------------------------------------------
    # 默认工厂
    # ------------------------------------------------------------------

    def _default_llm_client_factory(self) -> LLMClientProtocol:
        """默认 LLM 客户端工厂 — 从配置创建 LLMClient 实例。

        Returns:
            使用 UnifiedConfig 中 llm 字段配置的 LLMClient
        """
        from src.llm.llm_client import LLMClient

        llm = self._config.llm
        return LLMClient(
            api_key=llm.api_key,
            base_url=llm.base_url,
            model=llm.model,
        )

    def _default_permission_engine_factory(self) -> PermissionEngineProtocol:
        """默认权限引擎工厂 — 从配置加载 PermissionEngine。

        Returns:
            基于 UnifiedConfig 中 permissions 字段和 workspace 目录构建的权限引擎
        """
        from src.core.permission_engine import load_permission_engine

        return load_permission_engine(
            self._config.permissions,
            workspace=Path(self._config.workspace.dir),
        )

    def _default_permission_callback_factory(self) -> PermissionCallbackProtocol:
        """默认权限回调工厂 — 创建 CLI 交互式权限确认回调。

        Returns:
            超时时间为 120 秒的 CliCallback 实例
        """
        from src.runtime.permission_callback import CliCallback

        return CliCallback(timeout=120.0)

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def get_llm_client(self) -> LLMClientProtocol:
        """获取 LLM 客户端（懒加载单例）。

        Returns:
            已缓存的 LLMClientProtocol 实例，首次调用时通过工厂创建
        """
        if self._llm_client is None:
            self._llm_client = self._llm_client_factory()
        return self._llm_client

    def create_engine(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
    ) -> ReactEngine:
        """创建新的 ReactEngine 实例。

        每次调用均创建独立引擎，组装 LLM 客户端、权限引擎和权限回调。

        Args:
            api_key: 覆盖默认 API Key（None 则使用配置值）
            model: 覆盖默认模型（None 则使用配置值）
            max_iterations: 最大迭代次数（None 则使用引擎默认值）

        Returns:
            组装完成的 ReactEngine 实例
        """
        llm = self.get_llm_client()
        permission_engine = self._permission_engine_factory()
        permission_callback = self._permission_callback_factory()
        return ReactEngine(
            llm_client=llm,
            max_iterations=max_iterations,
            permission_engine=permission_engine,
            permission_callback=permission_callback,
        )


__all__ = ["AgentRuntime"]

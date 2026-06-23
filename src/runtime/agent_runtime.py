#!/usr/bin/env python3
"""AgentRuntime — 管理 LLM 客户端和引擎的创建与复用。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from src.config.unified_config import UnifiedConfig
from src.core.react_engine import ReactEngine
from src.mcp.config import MCPConfig
from src.permission import (
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)
from src.skills.loader import SkillLoader
from src.skills.registry import SkillRegistry
from src.skills.tool import set_registry as set_skill_registry
from src.tools.registry import ToolRegistry, _default_registry
from src.types.llm import LLMClientProtocol


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
        self._mcp_manager: Any = None
        self._skill_registry: SkillRegistry | None = None
        self._load_skills()

    # ------------------------------------------------------------------
    # 默认工厂
    # ------------------------------------------------------------------

    def _default_llm_client_factory(self) -> LLMClientProtocol:
        """默认 LLM 客户端工厂 — 从配置创建 LLMClient 实例。

        Returns:
            使用 UnifiedConfig 中 provider 配置的 LLMClient
        """
        from src.llm.llm_client import LLMClient

        api_key = ""
        base_url = None
        model = self._config.model or ""

        for pc in self._config.provider.values():
            if pc.options:
                if pc.options.apiKey:
                    api_key = pc.options.apiKey
                if pc.options.baseURL:
                    base_url = pc.options.baseURL

        return LLMClient(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

    def _default_permission_engine_factory(self) -> PermissionEngineProtocol:
        """默认权限引擎工厂 — 从配置加载 PermissionEngine。

        Returns:
            基于 UnifiedConfig 中 permissions 字段和 workspace 目录构建的权限引擎
        """
        from src.permission import load_permission_engine

        return load_permission_engine(
            self._config.permissions,
            workspace=Path(self._config.workspace.dir),
        )

    def _default_permission_callback_factory(self) -> PermissionCallbackProtocol:
        """默认权限回调工厂 — 创建 CLI 交互式权限确认回调。

        Returns:
            超时时间为 120 秒的 CliCallback 实例
        """
        from src.permission import CliCallback

        return CliCallback(timeout=120.0)

    # ------------------------------------------------------------------
    # Skill 加载
    # ------------------------------------------------------------------

    def _load_skills(self) -> None:
        """根据配置加载 skills 并设置全局 skill 工具引用。"""
        cfg = self._config.skills
        if not cfg.enabled:
            return

        workspace = Path(self._config.workspace.dir) if self._config.workspace.dir else Path.cwd()
        project_paths = [(workspace / p).expanduser().resolve() for p in cfg.project_paths]
        user_paths = [Path(p).expanduser().resolve() for p in cfg.user_paths]

        skills = SkillLoader.load(
            project_paths=project_paths,
            user_paths=user_paths,
        )

        if not skills:
            return

        registry = SkillRegistry()
        registry.load_all(skills)
        self._skill_registry = registry
        set_skill_registry(registry)

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

    async def start_mcp(self, registry: ToolRegistry | None = None) -> None:
        """启动 MCP 连接，注册 MCP 工具到注册表。

        配置中无 MCP 服务器时静默跳过。已启动时不再重复连接。

        Args:
            registry: 目标工具注册表，默认使用全局 _default_registry
        """
        if self._mcp_manager is not None:
            return
        mcp_data = self._config.mcp
        if not mcp_data or not mcp_data.get("servers"):
            return
        from src.mcp.manager import MCPClientManager

        mcp_config = MCPConfig.from_unified_config(mcp_data)
        target_registry = registry or _default_registry
        self._mcp_manager = MCPClientManager(mcp_config, target_registry)
        await self._mcp_manager.__aenter__()

    async def stop_mcp(self) -> None:
        """关闭所有 MCP 连接并清理资源。"""
        if self._mcp_manager is not None:
            mgr = self._mcp_manager
            self._mcp_manager = None
            await mgr.__aexit__(None, None, None)

    async def create_engine(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
    ) -> ReactEngine:
        """创建新的 ReactEngine 实例。

        每次调用均创建独立引擎，组装 LLM 客户端、权限引擎和权限回调。
        首次调用时自动启动 MCP 连接。

        Args:
            api_key: 覆盖默认 API Key（None 则使用配置值）
            model: 覆盖默认模型（None 则使用配置值）
            max_iterations: 最大迭代次数（None 则使用引擎默认值）

        Returns:
            组装完成的 ReactEngine 实例
        """
        await self.start_mcp()
        llm = self.get_llm_client()
        permission_engine = self._permission_engine_factory()
        permission_callback = self._permission_callback_factory()
        return ReactEngine(
            llm_client=llm,
            context_limit=self._config.get_model_context_limit(),
            max_steps=max_iterations if max_iterations else 50,
            permission_engine=permission_engine,
            permission_callback=permission_callback,
            skill_registry=self._skill_registry,
        )


__all__ = ["AgentRuntime"]

#!/usr/bin/env python3
"""AgentRuntime — 运行时组合根，管理 conversation 生命周期和 ReAct 引擎。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

from src.config.unified_config import UnifiedConfig
from src.core.react_engine import ReactEngine
from src.mcp.config import MCPConfig
from src.permission import (
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)
from src.runtime.conversation_manager import ConversationManager
from src.runtime.database_runtime import DatabaseRuntime
from src.runtime.engine_factory import EngineFactory
from src.skills.loader import SkillLoader
from src.skills.registry import SkillRegistry
from src.tools.registry import ToolRegistry, ToolRegistryFactory
from src.types.llm import LLMClientProtocol


class AgentRuntime:
    """Agent 运行时 — 管理会话状态、共享依赖和独立 ReactEngine。

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
        self._database_runtime = DatabaseRuntime(self._config.database.url)
        self._conversation_manager = ConversationManager(self._database_runtime.get_session_factory())
        self._tool_registry = self._create_tool_registry()
        self._engine_factory = self._create_engine_factory()

    def _create_tool_registry(self) -> ToolRegistry:
        factory = ToolRegistryFactory(
            session_factory_provider=self._database_runtime.get_session_factory,
            conversation_id_provider=lambda: self.conversation_id,
            agent_id="agent-001",
            skill_registry=self._skill_registry,
        )
        return factory.create_default()

    def _create_engine_factory(self) -> EngineFactory:
        return EngineFactory(
            config=self._config,
            llm_client_provider=self.get_llm_client,
            permission_engine_factory=self._permission_engine_factory,
            permission_callback_factory=self._permission_callback_factory,
            tool_registry=self._tool_registry,
            skill_registry=self._skill_registry,
        )

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
        """根据配置加载 skills。"""
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

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    @property
    def conversation_id(self) -> str | None:
        """当前 conversation ID，setup_conversation 后可用。"""
        return self._conversation_manager.conversation_id

    @property
    def is_new(self) -> bool:
        """当前 conversation 是否为新建。"""
        return self._conversation_manager.is_new

    @property
    def warnings(self) -> list[str]:
        """setup_conversation 过程中产生的警告列表。"""
        return self._conversation_manager.warnings

    async def initialize(self) -> None:
        """初始化数据库表结构。首次使用前必须调用。"""
        await self._database_runtime.initialize()

    async def setup_conversation(
        self,
        task: str,
        session_id: str | None = None,
        resume: bool = False,
    ) -> str:
        """创建或恢复 conversation 并注入 task/agent-team 上下文。

        Args:
            task: 初始任务描述（用作对话标题）
            session_id: 指定 conversation ID 继续
            resume: 从最近一次对话恢复

        Returns:
            conversation ID
        """
        return await self._conversation_manager.setup_conversation(task, session_id, resume)

    async def save_message(self, role: str, content: str) -> None:
        """将用户或 assistant 消息持久化到当前 conversation。

        Args:
            role: user 或 assistant
            content: 消息内容
        """
        await self._conversation_manager.save_message(role, content)

    async def list_conversations(self) -> list[dict[str, Any]]:
        """列出所有历史 conversation。"""
        return await self._conversation_manager.list_conversations()

    async def get_message_count(self, conversation_id: str) -> int:
        """获取指定 conversation 的消息数。"""
        return await self._conversation_manager.get_message_count(conversation_id)

    async def execute(self, task: str) -> AsyncGenerator[dict[str, Any], None]:
        """执行一轮对话：加载历史 → 创建引擎 → 流式执行 → 持久化回答。

        Args:
            task: 用户输入

        Yields:
            引擎事件流（thought/action/observation/answer）
        """
        if self.conversation_id is None:
            await self.setup_conversation(task)

        history_messages = await self._conversation_manager.load_history_messages()
        await self.save_message("user", task)

        engine = await self.create_engine()
        engine.load_history(history_messages)

        assistant_content = ""
        async for event in engine.iter_steps(task, reset_state=False):
            if event["type"] == "answer":
                assistant_content = event["data"]["answer"]
            yield event

        if assistant_content:
            await self.save_message("assistant", assistant_content)

    def get_llm_client(self) -> LLMClientProtocol:
        """获取 LLM 客户端（懒加载单例）。

        Returns:
            已缓存的 LLMClientProtocol 实例，首次调用时通过工厂创建
        """
        if self._llm_client is None:
            self._llm_client = self._llm_client_factory()
        return self._llm_client

    async def start_mcp(self) -> None:
        """启动 MCP 连接，注册 MCP 工具到注册表。

        配置中无 MCP 服务器时静默跳过。已启动时不再重复连接。

        """
        if self._mcp_manager is not None:
            return
        mcp_data = self._config.mcp
        if not mcp_data or not mcp_data.get("servers"):
            return
        from src.mcp.manager import MCPClientManager

        mcp_config = MCPConfig.from_unified_config(mcp_data)
        self._mcp_manager = MCPClientManager(mcp_config, self._tool_registry)
        await self._mcp_manager.__aenter__()

    async def stop_mcp(self) -> None:
        """关闭所有 MCP 连接并清理资源。"""
        if self._mcp_manager is not None:
            mgr = self._mcp_manager
            self._mcp_manager = None
            try:
                await mgr.__aexit__(None, None, None)
            except (asyncio.CancelledError, Exception):
                pass

    async def shutdown(self) -> None:
        """关闭 MCP 连接，释放运行时资源。"""
        await self.stop_mcp()
        await self._database_runtime.shutdown()

    async def create_engine(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> ReactEngine:
        """创建新的 ReactEngine 实例。

        每次调用均创建独立引擎，组装 LLM 客户端、权限引擎和权限回调。
        首次调用时自动启动 MCP 连接。

        Args:
            api_key: 覆盖默认 API Key（None 则使用配置值）
            model: 覆盖默认模型（None 则使用配置值）

        Returns:
            组装完成的 ReactEngine 实例
        """
        await self.start_mcp()
        return self._engine_factory.create()


__all__ = ["AgentRuntime"]

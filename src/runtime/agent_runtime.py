#!/usr/bin/env python3
"""AgentRuntime — 面向 CLI 的运行时门面。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, AsyncGenerator

from src.config.unified_config import UnifiedConfig
from src.permission import (
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)
from src.runtime.assembly import (
    build_runtime_components,
    create_default_llm_client,
    create_default_permission_callback,
    create_default_permission_engine,
)
from src.runtime.components import RuntimeComponents
from src.runtime.conversation_session import ConversationSession
from src.types.llm import LLMClientProtocol


class AgentRuntime:
    """Agent 运行时门面 — 管理会话生命周期并委托运行时组件执行。

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
        self._session: ConversationSession | None = None
        self._components: RuntimeComponents = build_runtime_components(
            config=self._config,
            llm_client_provider=self._get_llm_client,
            permission_engine_factory=self._permission_engine_factory,
            permission_callback_factory=self._permission_callback_factory,
        )

    # ------------------------------------------------------------------
    # 默认工厂
    # ------------------------------------------------------------------

    def _default_llm_client_factory(self) -> LLMClientProtocol:
        return create_default_llm_client(self._config)

    def _default_permission_engine_factory(self) -> PermissionEngineProtocol:
        """默认权限引擎工厂 — 从配置加载 PermissionEngine。

        Returns:
            基于 UnifiedConfig 中 permissions 字段和 workspace 目录构建的权限引擎
        """
        return create_default_permission_engine(self._config)

    def _default_permission_callback_factory(self) -> PermissionCallbackProtocol:
        """默认权限回调工厂 — 创建 CLI 交互式权限确认回调。

        Returns:
            超时时间为 120 秒的 CliCallback 实例
        """
        return create_default_permission_callback()

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    @property
    def conversation_id(self) -> str | None:
        """当前 conversation ID，setup_conversation 后可用。"""
        return self._components.conversation_service.conversation_id

    @property
    def is_new(self) -> bool:
        """当前 conversation 是否为新建。"""
        return self._components.conversation_service.is_new

    @property
    def warnings(self) -> list[str]:
        """setup_conversation 过程中产生的警告列表。"""
        return self._components.conversation_service.warnings

    async def initialize(self) -> None:
        """初始化数据库表结构。首次使用前必须调用。"""
        await self._components.database.initialize()

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
        return await self._components.conversation_service.setup_conversation(task, session_id, resume)

    async def list_conversations(self) -> list[dict[str, Any]]:
        """列出所有历史 conversation。"""
        return await self._components.conversation_service.list_conversations()

    async def get_message_count(self, conversation_id: str) -> int:
        """获取指定 conversation 的消息数。"""
        return await self._components.conversation_service.get_message_count(conversation_id)

    async def _get_or_create_session(self) -> ConversationSession:
        """获取或创建当前会话。

        首次调用时启动 MCP 并创建会话实例。
        会话持有 ReactEngine，跨轮复用，DB 仅在创建时查询一次。
        """
        # 会话已存在，直接返回内存态对象
        if self._session is None:
            # 首次：启动 MCP（幂等），创建 ConversationSession
            await self._components.mcp.start()
            cid = self._components.conversation_service.conversation_id
            assert cid is not None, "conversation_id 不能在未调用 setup_conversation 前使用"
            self._session = ConversationSession(
                conversation_id=cid,
                engine_factory=self._components.engine_factory,
                conversation_service=self._components.conversation_service,
            )
        return self._session

    async def execute(self, task: str) -> AsyncGenerator[dict[str, Any], None]:
        """执行一轮对话。

        ReactEngine 由 ConversationSession 持有并复用，不会每轮重建。
        DB 仅在会话首次创建时查询一次历史，后续轮次在内存中增量维护。

        Args:
            task: 用户输入

        Yields:
            引擎事件流（thought/action/observation/answer）
        """
        # 懒初始化：未调用 setup_conversation 时自动创建会话
        if self.conversation_id is None:
            await self.setup_conversation(task)

        # 获取/创建会话，委托 run_turn 执行（DB 查询仅发生在首次）
        session = await self._get_or_create_session()
        async for event in session.run_turn(task):
            yield event

    def _get_llm_client(self) -> LLMClientProtocol:
        """获取 LLM 客户端（懒加载单例）。

        Returns:
            已缓存的 LLMClientProtocol 实例，首次调用时通过工厂创建
        """
        if self._llm_client is None:
            self._llm_client = self._llm_client_factory()
        return self._llm_client

    async def shutdown(self) -> None:
        self._session = None
        await self._components.mcp.stop()
        await self._components.database.shutdown()


__all__ = ["AgentRuntime"]

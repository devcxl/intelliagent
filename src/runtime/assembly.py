"""Runtime assembly — 组装 AgentRuntime 背后的具体依赖。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.config.unified_config import UnifiedConfig
from src.permission import PermissionCallbackProtocol, PermissionEngineProtocol
from src.runtime.components import RuntimeComponents
from src.runtime.database_runtime import DatabaseRuntime
from src.runtime.engine_factory import EngineFactory
from src.runtime.mcp_integration import MCPIntegration
from src.services.conversation_service import ConversationService
from src.skills.registry import SkillRegistry
from src.tools.registry import ToolRegistry, ToolRegistryFactory
from src.types.llm import LLMClientProtocol
from src.utils.path_policy import PathPolicy


def build_runtime_components(
    config: UnifiedConfig,
    *,
    llm_client_provider: Callable[[], LLMClientProtocol],
    permission_engine_factory: Callable[[], PermissionEngineProtocol],
    permission_callback_factory: Callable[[], PermissionCallbackProtocol],
    conversation_id_provider: Callable[[], str | None] | None = None,
) -> RuntimeComponents:
    """根据配置组装 AgentRuntime 需要的运行时组件。"""
    skill_registry = load_skill_registry(config)
    database = DatabaseRuntime(config.database.url)
    conversation_service = ConversationService(database.get_session_factory())
    tool_registry = create_tool_registry(
        config=config,
        database=database,
        skill_registry=skill_registry,
        conversation_id_provider=conversation_id_provider or (lambda: conversation_service.conversation_id),
    )
    mcp = MCPIntegration(config.mcp, tool_registry)
    engine_factory = EngineFactory(
        config=config,
        llm_client_provider=llm_client_provider,
        permission_engine_factory=permission_engine_factory,
        permission_callback_factory=permission_callback_factory,
        tool_registry=tool_registry,
        skill_registry=skill_registry,
    )
    return RuntimeComponents(
        database=database,
        conversation_service=conversation_service,
        tool_registry=tool_registry,
        mcp=mcp,
        engine_factory=engine_factory,
    )


def create_tool_registry(
    *,
    config: UnifiedConfig,
    database: DatabaseRuntime,
    skill_registry: SkillRegistry | None,
    conversation_id_provider: Callable[[], str | None],
) -> ToolRegistry:
    path_policy = PathPolicy(
        workspace=Path(config.workspace.dir),
        external_directories=tuple(Path(d) for d in config.permissions.external_directories),
    )
    factory = ToolRegistryFactory(
        session_factory_provider=database.get_session_factory,
        conversation_id_provider=conversation_id_provider,
        agent_id=config.agent_id,
        skill_registry=skill_registry,
        agent_team_enabled=config.agent_team.enabled,
        path_policy=path_policy,
    )
    return factory.create_default()


def load_skill_registry(config: UnifiedConfig) -> SkillRegistry | None:
    from src.skills.runtime import SkillRuntime

    workspace = Path(config.workspace.dir) if config.workspace.dir else Path.cwd()
    runtime = SkillRuntime(config.skills, workspace)
    return runtime.load_registry()


def create_default_llm_client(config: UnifiedConfig) -> LLMClientProtocol:
    from src.llm.factory import LLMClientFactory

    return LLMClientFactory(config).create()


def create_default_permission_engine(config: UnifiedConfig) -> PermissionEngineProtocol:
    from src.permission import load_permission_engine

    return load_permission_engine(
        config.permissions,
        workspace=Path(config.workspace.dir),
    )


def create_default_permission_callback() -> PermissionCallbackProtocol:
    from src.permission import CliCallback

    return CliCallback(timeout=120.0)


__all__ = [
    "build_runtime_components",
    "create_default_llm_client",
    "create_default_permission_callback",
    "create_default_permission_engine",
]

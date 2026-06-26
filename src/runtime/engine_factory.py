"""EngineFactory — 组装 ReactEngine 的专职工厂。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.config.unified_config import UnifiedConfig
from src.core.react_engine import ReactEngine
from src.permission import PermissionCallbackProtocol, PermissionEngineProtocol
from src.skills.registry import SkillRegistry
from src.tools.registry import ToolRegistry
from src.types.llm import LLMClientProtocol


class EngineFactory:
    """集中组装 ReactEngine，避免 AgentRuntime 了解过多构造细节。"""

    def __init__(
        self,
        config: UnifiedConfig,
        llm_client_provider: Callable[[], LLMClientProtocol],
        permission_engine_factory: Callable[[], PermissionEngineProtocol],
        permission_callback_factory: Callable[[], PermissionCallbackProtocol],
        tool_registry: ToolRegistry,
        skill_registry: SkillRegistry | None,
    ) -> None:
        self._config = config
        self._llm_client_provider = llm_client_provider
        self._permission_engine_factory = permission_engine_factory
        self._permission_callback_factory = permission_callback_factory
        self._tool_registry = tool_registry
        self._skill_registry = skill_registry

    def create(
        self,
        compact_callback: Callable[[list[str], str], Awaitable[None]] | None = None,
    ) -> ReactEngine:
        return ReactEngine(
            llm_client=self._llm_client_provider(),
            tools_registry=self._tool_registry,
            context_limit=self._config.get_model_context_limit(),
            permission_engine=self._permission_engine_factory(),
            permission_callback=self._permission_callback_factory(),
            skill_registry=self._skill_registry,
            compact_callback=compact_callback,
        )


__all__ = ["EngineFactory"]

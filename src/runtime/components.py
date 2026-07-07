"""RuntimeComponents — AgentRuntime 背后的具体运行时依赖。"""

from __future__ import annotations

from dataclasses import dataclass

from src.runtime.database_runtime import DatabaseRuntime
from src.runtime.engine_factory import EngineFactory
from src.runtime.mcp_integration import MCPIntegration
from src.services.conversation_service import ConversationService
from src.tools.registry import ToolRegistry


@dataclass
class RuntimeComponents:
    """AgentRuntime 使用的一组已装配运行时组件。"""

    database: DatabaseRuntime
    conversation_service: ConversationService
    tool_registry: ToolRegistry
    mcp: MCPIntegration
    engine_factory: EngineFactory


__all__ = ["RuntimeComponents"]

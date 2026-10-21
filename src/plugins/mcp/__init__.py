"""mcp 内置插件（Built-in Plugin）：MCP 服务器工具注册为 Tool Capability，inputSchema 完整透传（US16）。"""

from src.plugins.mcp.config import McpPluginConfig, McpServerConfig
from src.plugins.mcp.connection import McpCallResult, McpConnection, McpConnector, McpToolDefinition
from src.plugins.mcp.errors import McpConnectionError, McpPluginError, McpToolConflictError
from src.plugins.mcp.plugin import PLUGIN_NAME, McpPlugin, capability_name
from src.plugins.mcp.tools import McpTool

__all__ = [
    "PLUGIN_NAME",
    "McpCallResult",
    "McpConnection",
    "McpConnectionError",
    "McpConnector",
    "McpPlugin",
    "McpPluginConfig",
    "McpPluginError",
    "McpServerConfig",
    "McpTool",
    "McpToolConflictError",
    "McpToolDefinition",
    "capability_name",
]

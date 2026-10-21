"""mcp 插件错误层次：连接失败含 server 标识与原因，工具名冲突显式报错。"""

from __future__ import annotations


class McpPluginError(Exception):
    """mcp 插件错误基类。"""


class McpConnectionError(McpPluginError):
    """MCP 服务器连接失败：server 是服务器标识，reason 是可诊断原因（含底层异常）。"""

    def __init__(self, server: str, reason: str) -> None:
        super().__init__(f"MCP server '{server}' connection failed: {reason}")
        self.server = server
        self.reason = reason


class McpToolConflictError(McpPluginError):
    """两个 MCP 工具映射到同一能力名：显式报错（含双方来源），绝不静默覆盖。"""

    def __init__(self, capability: str, first: tuple[str, str], second: tuple[str, str]) -> None:
        first_server, first_tool = first
        second_server, second_tool = second
        super().__init__(
            f"MCP tool name conflict: capability '{capability}' is produced by "
            f"server '{first_server}' tool '{first_tool}' and by server '{second_server}' tool '{second_tool}'"
        )
        self.capability = capability
        self.first = first
        self.second = second

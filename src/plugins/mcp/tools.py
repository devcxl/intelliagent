"""MCP 工具能力提供者：inputSchema 原样透传，tools/call 结果转统一结果信封（ToolProvider 契约）。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.plugins.basic_tools.result import tool_error, tool_success
from src.plugins.mcp.connection import McpConnection


@dataclass(frozen=True)
class McpTool:
    """注册为 CapabilityKind.TOOL 的 MCP 工具（CONTEXT 术语：Tool）。

    parameters 就是 MCP inputSchema 原样：嵌套 object/enum/items/oneOf 不降级，模型可正确构造复杂参数。
    name 是能力名（mcp_{server}_{tool}）；tool_name 是发给服务器的原始工具名，两者不必相同。
    """

    name: str
    server: str
    tool_name: str
    parameters: Mapping[str, Any]
    connection: McpConnection

    async def run(self, **kwargs: Any) -> str:
        """调用 MCP tools/call 并转统一信封：isError 与传输异常都收敛为 status="error"（可诊断）。"""
        try:
            result = await self.connection.call_tool(self.tool_name, kwargs)
        except Exception as exc:
            return tool_error(
                "MCP_CALL_FAILED",
                f"MCP server '{self.server}' tool '{self.tool_name}' call failed: {exc}",
                server=self.server,
                tool=self.tool_name,
            )
        if result.is_error:
            return tool_error(
                "MCP_TOOL_ERROR",
                result.text or f"MCP server '{self.server}' tool '{self.tool_name}' failed without an error message",
                server=self.server,
                tool=self.tool_name,
            )
        return tool_success(content=result.text, server=self.server, tool=self.tool_name)

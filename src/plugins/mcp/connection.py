"""MCP 连接接缝：插件只依赖这里的协议，真实传输（mcp SDK）与测试 fake 在连接器一侧替换。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from src.plugins.mcp.config import McpServerConfig


@dataclass(frozen=True)
class McpToolDefinition:
    """MCP 服务器发现的一条工具定义；input_schema 是 MCP inputSchema 原样（不降级、不扁平化）。"""

    name: str
    description: str
    input_schema: Mapping[str, Any]


@dataclass(frozen=True)
class McpCallResult:
    """MCP tools/call 的统一结果：text 是内容块拼接文本，is_error 对应 CallToolResult.isError。"""

    text: str
    is_error: bool


class McpSession(Protocol):
    """已建立的 MCP 会话：工具发现与调用。"""

    async def list_tools(self) -> Sequence[McpToolDefinition]: ...

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> McpCallResult: ...


class McpConnection(McpSession, Protocol):
    """一条可关闭的服务器连接（McpSession + 生命周期收尾）。"""

    async def close(self) -> None: ...


class McpConnector(Protocol):
    """MCP 连接器：按配置建立单个服务器的连接。实现负责传输细节与生命周期安全。"""

    async def connect(self, server: McpServerConfig) -> McpConnection: ...

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mcp.types import CallToolResult

from mcp import ClientSession, StdioServerParameters, stdio_client
from src.mcp.config import MCPConfig, MCPServerConfig
from src.tools.registry import ToolRegistry
from src.utils.logger import logger

MCP_TOOL_PREFIX = "mcp_"


@dataclass
class _ServerConnection:
    name: str
    config: MCPServerConfig
    registered_tools: list[str] = field(default_factory=list)
    failed: bool = False

    _session: ClientSession | None = field(default=None, repr=False)
    _stdio_ctx: Any = field(default=None, repr=False)
    _read_stream: Any = field(default=None, repr=False)
    _write_stream: Any = field(default=None, repr=False)


def _mcp_tool_name(server_name: str, tool_name: str) -> str:
    """生成 MCP 工具在注册表中的唯一名称。

    Args:
        server_name: MCP 服务器名称
        tool_name: 工具原始名称

    Returns:
        带 mcp_ 前缀和服务器名的工具标识，格式为 mcp_{server_name}_{tool_name}
    """
    return f"{MCP_TOOL_PREFIX}{server_name}_{tool_name}"


def _tool_params_to_openai(input_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """将 MCP inputSchema 转为 ToolRegistry 兼容的 parameters 格式。

    Args:
        input_schema: MCP 工具返回的 inputSchema 字典，包含 properties 和 required 字段

    Returns:
        键为参数名、值为 {type, description, required} 的参数字典
    """
    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))
    result: dict[str, dict[str, Any]] = {}
    for pname, pinfo in properties.items():
        result[pname] = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
            "required": pname in required,
        }
    return result


def _format_mcp_result(result: CallToolResult) -> str:
    """将 MCP CallToolResult 转为 JSON 字符串。

    Args:
        result: MCP 工具调用返回的 CallToolResult 对象

    Returns:
        成功时返回 content 文本拼接结果，失败时返回 {"status": "error", "error": ...} JSON
    """
    parts: list[str] = []
    for item in result.content:
        if hasattr(item, "text") and item.text:
            parts.append(item.text)
        elif hasattr(item, "data") and item.data:
            parts.append(str(item.data))
    text = "\n".join(parts)
    if result.isError:
        import json

        return json.dumps({"status": "error", "error": text or "MCP 工具执行失败"}, ensure_ascii=False)
    return text


class MCPClientManager:
    """管理 N 个 MCP Server 连接，生命周期由 async with 控制。

    通过 async with 进入时自动连接所有配置的 MCP 服务器，
    将各服务器的工具注册到 ToolRegistry 中。
    退出时自动注销工具并关闭所有连接。
    """

    def __init__(self, config: MCPConfig, registry: ToolRegistry) -> None:
        """初始化 MCP 客户端管理器。

        Args:
            config: MCP 配置，包含要连接的服务器列表
            registry: 工具注册表，MCP 工具将注册到此实例
        """
        self._config = config
        self._registry = registry
        self._connections: list[_ServerConnection] = []

    async def __aenter__(self) -> MCPClientManager:
        """异步上下文管理器入口，依次连接所有 MCP 服务器。

        Returns:
            self，连接完成后的 MCPClientManager 实例
        """
        for server in self._config.servers:
            conn = await self._connect_server(server)
            self._connections.append(conn)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """异步上下文管理器出口，关闭所有连接并清理资源。

        Args:
            exc_type: 异常类型（如有）
            exc_val: 异常值（如有）
            exc_tb: 异常 traceback（如有）
        """
        for conn in self._connections:
            try:
                await self._close_connection(conn)
            except Exception as e:
                logger.error("MCP 服务器关闭失败 | server=%s error=%s", conn.name, e)
        self._connections.clear()

    async def _connect_server(self, server: MCPServerConfig) -> _ServerConnection:
        """连接单个 MCP 服务器并注册其工具。

        Args:
            server: 单个 MCP 服务器配置

        Returns:
            _ServerConnection 实例，包含连接状态和已注册工具列表
        """
        conn = _ServerConnection(name=server.name, config=server)
        try:
            if server.transport == "sse":
                if not server.url:
                    raise ValueError("SSE transport 需要 url 字段")
                from mcp.client.sse import sse_client

                sse_ctx = sse_client(
                    url=server.url,
                    headers=server.headers,
                    timeout=server.timeout,
                    sse_read_timeout=server.sse_read_timeout,
                )
                read_stream, write_stream = await sse_ctx.__aenter__()
                conn._read_stream = read_stream
                conn._write_stream = write_stream
                conn._stdio_ctx = sse_ctx
            else:
                params = StdioServerParameters(
                    command=server.command,
                    args=server.args,
                    env=server.env,
                    cwd=server.cwd,
                )
                stdio_ctx = stdio_client(params)
                read_stream, write_stream = await stdio_ctx.__aenter__()
                conn._read_stream = read_stream
                conn._write_stream = write_stream
                conn._stdio_ctx = stdio_ctx

            session = ClientSession(read_stream, write_stream)
            await session.__aenter__()
            await session.initialize()
            conn._session = session

            tools_result = await session.list_tools()
            registered: list[str] = []
            for tool in tools_result.tools:
                mcp_name = _mcp_tool_name(server.name, tool.name)
                params = _tool_params_to_openai(tool.inputSchema)

                async def call_mcp_tool(
                    tool_name: str = tool.name,
                    session: ClientSession = session,
                    **kwargs: Any,
                ) -> str:
                    result = await session.call_tool(tool_name, arguments=kwargs)
                    return _format_mcp_result(result)

                self._registry.register(
                    fn=call_mcp_tool,
                    name=mcp_name,
                    description=tool.description or "",
                    parameters=params,
                )
                registered.append(mcp_name)

            conn.registered_tools = registered
            logger.info(
                "MCP 服务器已连接 | server=%s tools=%d",
                server.name,
                len(registered),
            )
        except Exception as e:
            conn.failed = True
            logger.error("MCP 服务器连接失败 | server=%s error=%s", server.name, e)
            await self._close_connection(conn)
        return conn

    async def _close_connection(self, conn: _ServerConnection) -> None:
        """关闭单个 MCP 服务器连接并清理资源。

        按顺序：注销工具 → 关闭 session → 关闭 stdio 上下文。
        所有操作在同一 task 中执行，避免 anyio CancelScope 跨 task 问题。
        """
        for tool_name in conn.registered_tools:
            self._registry.unregister(tool_name)
        conn.registered_tools.clear()

        if conn._session is not None:
            try:
                await conn._session.__aexit__(None, None, None)
            except Exception:
                pass
            conn._session = None

        if conn._stdio_ctx is not None:
            try:
                await conn._stdio_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            conn._stdio_ctx = None
            conn._read_stream = None
            conn._write_stream = None

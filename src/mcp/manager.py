from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from mcp.types import CallToolResult

from mcp import ClientSession, StdioServerParameters, stdio_client
from src.mcp.config import MCPConfig, MCPServerConfig
from src.tools.registry import ToolRegistry
from src.utils.logger import logger

MCP_TOOL_PREFIX = "mcp_"
_PROCESS_CLEANUP_TIMEOUT = 10


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
    return f"{MCP_TOOL_PREFIX}{server_name}_{tool_name}"


def _tool_params_to_openai(input_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """将 MCP inputSchema 转为 ToolRegistry 兼容的 parameters 格式。"""
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
    """将 MCP CallToolResult 转为 JSON 字符串。"""
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
    """管理 N 个 MCP Server 连接，生命周期由 async with 控制。"""

    def __init__(self, config: MCPConfig, registry: ToolRegistry) -> None:
        self._config = config
        self._registry = registry
        self._connections: list[_ServerConnection] = []

    async def __aenter__(self) -> MCPClientManager:
        for server in self._config.servers:
            conn = await self._connect_server(server)
            self._connections.append(conn)
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        results = await asyncio.gather(
            *(self._close_connection(c) for c in self._connections),
            return_exceptions=True,
        )
        for name, r in zip([c.name for c in self._connections], results):
            if isinstance(r, Exception):
                logger.error("MCP 服务器关闭失败 | server=%s error=%s", name, r)
        self._connections.clear()

    async def _connect_server(self, server: MCPServerConfig) -> _ServerConnection:
        conn = _ServerConnection(name=server.name, config=server)
        try:
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
        for tool_name in conn.registered_tools:
            self._registry.unregister(tool_name)
        conn.registered_tools.clear()

        exc = None
        if conn._session is not None:
            try:
                await conn._session.__aexit__(None, None, None)
            except Exception as e:
                exc = e
                logger.warning("MCP session 关闭异常 | server=%s error=%s", conn.name, e)
            conn._session = None

        if conn._stdio_ctx is not None:
            try:
                async with asyncio.timeout(_PROCESS_CLEANUP_TIMEOUT):
                    await conn._stdio_ctx.__aexit__(None, None, None)
            except TimeoutError:
                logger.warning("MCP 进程关闭超时 | server=%s", conn.name)
            except Exception as e:
                if exc is None:
                    exc = e
                logger.warning("MCP stdio 关闭异常 | server=%s error=%s", conn.name, e)
            conn._stdio_ctx = None

        if exc is not None and not conn.failed:
            raise exc  # type: ignore[misc]

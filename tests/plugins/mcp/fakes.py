"""mcp 插件测试用 fake：内存连接器与工具定义，不触网络与子进程。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from src.plugins.mcp.config import McpPluginConfig, McpServerConfig
from src.plugins.mcp.connection import McpCallResult, McpConnection, McpToolDefinition

NESTED_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "description": "检索词"},
        "mode": {"type": "string", "enum": ["fast", "thorough"]},
        "filters": {
            "type": "object",
            "properties": {
                "tags": {"type": "array", "items": {"type": "string"}},
                "limits": {
                    "type": "object",
                    "properties": {
                        "max": {"type": "integer", "minimum": 1},
                        "unit": {"type": "string", "enum": ["kb", "mb"]},
                    },
                    "required": ["max"],
                },
            },
            "required": ["tags"],
        },
        "targets": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "depth": {"type": "integer"}},
                "required": ["path"],
            },
        },
    },
    "required": ["query"],
}


def tool_definition(name: str, *, schema: Mapping[str, Any] | None = None, description: str = "") -> McpToolDefinition:
    """构造一条 MCP 工具定义；默认携带 NESTED_INPUT_SCHEMA。"""
    return McpToolDefinition(name=name, description=description, input_schema=dict(schema or NESTED_INPUT_SCHEMA))


class FakeConnection:
    """内存 McpConnection：记录调用、按工具名返回预置结果，可注入调用异常。"""

    def __init__(
        self,
        tools: Sequence[McpToolDefinition] = (),
        *,
        results: Mapping[str, McpCallResult] | None = None,
        default_result: McpCallResult | None = None,
        call_error: Exception | None = None,
        list_tools_delay: float | None = None,
    ) -> None:
        self.tools = list(tools)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self._results = dict(results or {})
        self._default_result = default_result or McpCallResult(text="ok", is_error=False)
        self._call_error = call_error
        self._list_tools_delay = list_tools_delay

    async def list_tools(self) -> Sequence[McpToolDefinition]:
        if self._list_tools_delay is not None:
            await asyncio.sleep(self._list_tools_delay)
        return list(self.tools)

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> McpCallResult:
        self.calls.append((name, dict(arguments)))
        if self._call_error is not None:
            raise self._call_error
        return self._results.get(name, self._default_result)

    async def close(self) -> None:
        self.closed = True


class FakeConnector:
    """内存 McpConnector：按服务器名给出连接，可注入连接异常与连接延迟。"""

    def __init__(
        self,
        connections: Mapping[str, FakeConnection] | None = None,
        *,
        connect_errors: Mapping[str, Exception] | None = None,
        connect_delays: Mapping[str, float] | None = None,
    ) -> None:
        self._connections = dict(connections or {})
        self._connect_errors = dict(connect_errors or {})
        self._connect_delays = dict(connect_delays or {})
        self.connected: list[str] = []

    async def connect(self, server: McpServerConfig) -> McpConnection:
        self.connected.append(server.name)
        delay = self._connect_delays.get(server.name)
        if delay is not None:
            await asyncio.sleep(delay)
        error = self._connect_errors.get(server.name)
        if error is not None:
            raise error
        return self._connections[server.name]


def demo_server(name: str = "demo", **overrides: Any) -> McpServerConfig:
    """构造测试用 stdio 服务器配置。"""
    return McpServerConfig(name=name, transport="stdio", command=["fake-mcp-server"], **overrides)


def demo_config(*names: str) -> McpPluginConfig:
    """构造仅含 stdio 服务器的插件配置；未给名字时默认单个 "demo" 服务器。"""
    return McpPluginConfig(servers=[demo_server(name) for name in (names or ("demo",))])

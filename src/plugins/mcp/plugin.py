"""mcp 内置插件：连接 MCP 服务器，发现工具并注册为 Tool Capability（US16）。

生命周期：`await connect()` 连接服务器并发现工具 → `PluginHost.load(plugin)` 注册能力 → `await close()` 关闭。
连接先于注册：能力清单来自运行时发现，Manifest 只能在 connect 之后给出（未连接就 load 报可诊断错误）。
任一服务器连接失败即整体失败并关闭已开连接——能力缺失即功能缺失，不静默降级（CONTEXT 设计原则）。
"""

from __future__ import annotations

import asyncio
import contextlib
import re
from collections.abc import Sequence

from pydantic import BaseModel

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest
from src.plugins.mcp.config import McpPluginConfig, McpServerConfig
from src.plugins.mcp.connection import McpConnection, McpConnector, McpToolDefinition
from src.plugins.mcp.errors import McpConnectionError, McpPluginError, McpToolConflictError
from src.plugins.mcp.tools import McpTool

PLUGIN_NAME = "mcp"
CAPABILITY_PREFIX = "mcp_"
PLUGIN_VERSION = "0.1.0"

_UNSAFE_NAME_CHARS = re.compile(r"[^a-z0-9._-]")


def capability_name(server: str, tool: str) -> str:
    """MCP 工具的能力名：mcp_{server}_{tool}。

    工具名按 Capability 命名约束规范化（小写、非法字符转 "_"）；规范化引发的重名在发现期显式报错。
    """
    return f"{CAPABILITY_PREFIX}{server}_{_UNSAFE_NAME_CHARS.sub('_', tool.lower())}"


class McpPlugin:
    """CONTEXT 术语：Built-in Plugin——与外部插件走同一注册契约，区别仅在发现方式（ADR 0007）。

    用法：`await plugin.connect()` → `PluginHost.load(plugin)` → ... → `await plugin.close()`。
    """

    def __init__(self, config: McpPluginConfig, connector: McpConnector | None = None) -> None:
        self._config = config
        self._connector = connector if connector is not None else _default_connector()
        self._connections: list[tuple[str, McpConnection]] = []
        self._tools: list[McpTool] = []
        self._manifest: Manifest | None = None

    @property
    def manifest(self) -> Manifest:
        """插件 Manifest：能力清单来自 connect 的发现结果，未连接就访问给出可诊断错误。"""
        if self._manifest is None:
            raise McpPluginError("mcp plugin is not connected; call await plugin.connect() before loading it")
        return self._manifest

    async def connect(self) -> None:
        """连接配置中的全部 MCP 服务器并发现工具，构建 Manifest 能力清单。

        每台服务器的「连接 + 工具发现」受 connect_timeout 显式封顶；
        连接失败、超时或工具名冲突都会清理已开连接并抛出可诊断错误。
        """
        if self._manifest is not None:
            raise McpPluginError("mcp plugin is already connected")
        discovered: list[tuple[str, McpServerConfig, McpConnection, McpToolDefinition]] = []
        owners: dict[str, tuple[str, str]] = {}
        try:
            for server in self._config.servers:
                connection, tools = await self._connect_server(server)
                self._connections.append((server.name, connection))
                for tool in tools:
                    name = capability_name(server.name, tool.name)
                    if name in owners:
                        raise McpToolConflictError(name, owners[name], (server.name, tool.name))
                    owners[name] = (server.name, tool.name)
                    discovered.append((name, server, connection, tool))
            self._manifest = self._build_manifest(discovered)
        except BaseException:
            await _close_quietly([connection for _name, connection in self._connections])
            self._connections.clear()
            raise
        self._tools = [
            McpTool(
                name=name,
                server=server.name,
                tool_name=tool.name,
                description=tool.description,
                parameters=tool.input_schema,
                connection=connection,
                call_timeout=server.timeout,
            )
            for name, server, connection, tool in discovered
        ]

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        """把 connect 发现的工具全部注册为 Tool Capability 提供者（McpTool）。

        配置在 connect() 时消费：服务器连接先于能力注册，能力清单由发现决定，此处仅校验类型。
        """
        if config is not None and not isinstance(config, McpPluginConfig):
            raise TypeError(f"mcp plugin expects McpPluginConfig, got {type(config).__name__}")
        if self._manifest is None:
            raise McpPluginError("mcp plugin is not connected; call await plugin.connect() before loading it")
        for tool in self._tools:
            registrar.register(CapabilityKind.TOOL, tool.name, tool)

    async def close(self) -> None:
        """关闭全部服务器连接（幂等）；全部尝试后仍失败时抛出首个错误。"""
        connections, self._connections = self._connections, []
        self._tools = []
        self._manifest = None
        first_error: McpConnectionError | None = None
        for server_name, connection in connections:
            try:
                await connection.close()
            except Exception as exc:
                if first_error is None:
                    first_error = McpConnectionError(server_name, f"failed to close: {exc}")
        if first_error is not None:
            raise first_error

    async def _connect_server(self, server: McpServerConfig) -> tuple[McpConnection, list[McpToolDefinition]]:
        """连接单个服务器并发现工具；失败/超时都关闭半开连接并抛 McpConnectionError。"""
        connection: McpConnection | None = None
        try:
            async with asyncio.timeout(server.connect_timeout):
                connection = await self._connector.connect(server)
                return connection, list(await connection.list_tools())
        except TimeoutError as exc:
            await _close_quietly([connection] if connection is not None else [])
            raise McpConnectionError(server.name, f"connection timed out after {server.connect_timeout:g}s") from exc
        except McpConnectionError:
            await _close_quietly([connection] if connection is not None else [])
            raise
        except Exception as exc:
            await _close_quietly([connection] if connection is not None else [])
            raise McpConnectionError(server.name, f"{type(exc).__name__}: {exc}") from exc

    def _build_manifest(
        self, discovered: Sequence[tuple[str, McpServerConfig, McpConnection, McpToolDefinition]]
    ) -> Manifest:
        if not discovered:
            server_names = ", ".join(server.name for server in self._config.servers) or "<none>"
            raise McpPluginError(f"no MCP tools discovered on servers [{server_names}]; nothing to register")
        return Manifest(
            name=PLUGIN_NAME,
            version=PLUGIN_VERSION,
            api_version=1,
            capabilities=tuple(
                CapabilityDeclaration(kind=CapabilityKind.TOOL, name=name) for name, _server, _conn, _tool in discovered
            ),
            config_schema=McpPluginConfig,
        )


async def _close_quietly(connections: Sequence[McpConnection | None]) -> None:
    """失败路径的清理：尽力关闭，不让清理错误掩盖真正的失败原因。"""
    for connection in connections:
        if connection is None:
            continue
        with contextlib.suppress(Exception):
            await connection.close()


def _default_connector() -> McpConnector:
    """默认连接器（mcp SDK）。延迟导入：只有真实连接才需要 SDK 依赖，测试注入 fake 不需要。"""
    from src.plugins.mcp.sdk_connector import McpSdkConnector

    return McpSdkConnector()

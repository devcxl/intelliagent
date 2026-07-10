from __future__ import annotations

import asyncio
from typing import Any

from src.mcp.config import MCPConfig
from src.tools.registry import ToolRegistry


class MCPIntegration:
    """管理 MCP 服务器连接的启动、关闭和生命周期。

    持有 MCPClientManager，将其工具注册到 ToolRegistry。
    """

    def __init__(self, mcp_data: dict, tool_registry: ToolRegistry) -> None:
        self._mcp_data = mcp_data
        self._tool_registry = tool_registry
        self._manager: Any = None

    async def start(self) -> None:
        """启动所有 MCP 服务器连接。已启动时跳过。"""
        if self._manager is not None:
            return
        if not self._mcp_data:
            return
        from src.mcp.manager import MCPClientManager

        mcp_config = MCPConfig.from_unified_config(self._mcp_data)
        self._manager = MCPClientManager(mcp_config, self._tool_registry)
        await self._manager.__aenter__()

    async def stop(self) -> None:
        """关闭所有 MCP 连接。"""
        if self._manager is not None:
            mgr = self._manager
            self._manager = None
            try:
                await mgr.__aexit__(None, None, None)
            except (asyncio.CancelledError, Exception):
                pass

    @property
    def is_running(self) -> bool:
        return self._manager is not None

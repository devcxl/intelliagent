#!/usr/bin/env python3
"""
工具注册中心 - 完全 MCP 模式
直接使用 MCP Server 提供的工具，不使用混合模式
"""
from core.tool_registry_mcp import ToolRegistry as MCPToolRegistry
from utils.logger import logger


class ToolRegistry:
    """
    工具注册中心 - 完全 MCP 模式
    要求 MCP Server 必须可用
    """

    def __init__(self):
        """初始化 MCP 工具注册中心"""
        try:
            self._mcp_registry = MCPToolRegistry()
            logger.info("✅ MCP 工具注册中心已初始化")
        except Exception as e:
            logger.error(f"❌ MCP 初始化失败: {e}")
            raise RuntimeError(
                "MCP Server 不可用，请检查配置或启动 MCP Server"
            ) from e

    def initialize(self):
        """初始化工具注册中心"""
        self._mcp_registry.initialize()

    def get_tool(self, name: str):
        """获取工具"""
        return self._mcp_registry.get_tool(name)

    def describe_tools(self) -> str:
        """描述所有工具"""
        return self._mcp_registry.describe_tools()

    def list_tools(self):
        """列出所有可用工具"""
        return self._mcp_registry.list_tools()

    def cleanup(self):
        """清理资源"""
        try:
            self._mcp_registry.cleanup()
            logger.info("✅ MCP 资源已清理")
        except Exception as e:
            logger.error(f"❌ MCP 清理时出错: {e}")
            raise


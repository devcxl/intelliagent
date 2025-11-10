#!/usr/bin/env python3
"""
MCP 工具注册中心
通过 MCP 协议连接到工具服务器，提供工具调用接口
"""
import json
import asyncio
from typing import Dict, Any, Optional, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from utils.logger import logger
from utils.config import MCP_SERVER_COMMAND, MCP_SERVER_SCRIPT


class ToolRegistry:
    """MCP 工具注册中心 - 完全基于 MCP 协议"""

    def __init__(self):
        """初始化 MCP 客户端"""
        self.session: Optional[ClientSession] = None
        self.tools: Dict[str, Any] = {}
        self._initialized = False
        self._loop = None
        self._stdio_context = None
        self.read = None
        self.write = None

    def _get_or_create_event_loop(self):
        """获取或创建事件循环"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    async def _init_async(self):
        """异步初始化 MCP 连接"""
        if self._initialized:
            return

        try:
            # 配置 MCP 服务器参数
            server_params = StdioServerParameters(
                command=MCP_SERVER_COMMAND,
                args=[MCP_SERVER_SCRIPT],
                env=None
            )

            # 建立连接（不使用 async with，手动管理生命周期）
            self._stdio_context = stdio_client(server_params)
            self.read, self.write = await self._stdio_context.__aenter__()

            # 创建会话（不使用 async with，手动管理）
            self.session = ClientSession(self.read, self.write)
            await self.session.__aenter__()

            # 初始化会话
            await self.session.initialize()

            # 列出可用工具
            response = await self.session.list_tools()
            self.tools = {tool.name: tool for tool in response.tools}

            logger.info(f"✅ MCP 工具注册中心已连接，可用工具: {list(self.tools.keys())}")
            self._initialized = True

        except Exception as e:
            logger.error(f"❌ MCP 初始化失败: {e}")
            raise RuntimeError(f"无法连接到 MCP 服务器: {e}") from e

    def initialize(self):
        """同步初始化入口"""
        if self._initialized:
            return

        self._loop = self._get_or_create_event_loop()
        self._loop.run_until_complete(self._init_async())

    async def _call_tool_async(self, name: str, arguments: Dict[str, Any]) -> Any:
        """异步调用工具"""
        if not self._initialized:
            await self._init_async()

        if name not in self.tools:
            raise ValueError(f"工具 '{name}' 不存在")

        try:
            result = await self.session.call_tool(name, arguments)

            # 解析结果
            if result.content:
                content = result.content[0]
                if hasattr(content, 'text'):
                    response_data = json.loads(content.text)
                    if response_data.get("status") == "ok":
                        return response_data
                    else:
                        raise RuntimeError(response_data.get("error", "未知错误"))

            return {"status": "ok", "result": str(result)}

        except Exception as e:
            logger.error(f"❌ 调用工具 '{name}' 失败: {e}")
            raise

    def get_tool(self, name: str):
        """获取工具的包装器"""
        if not self._initialized:
            self.initialize()

        def tool_wrapper(**kwargs):
            """工具调用包装器"""
            loop = self._get_or_create_event_loop()
            return loop.run_until_complete(
                self._call_tool_async(name, kwargs)
            )

        return tool_wrapper

    def describe_tools(self) -> str:
        """描述所有可用工具"""
        if not self._initialized:
            self.initialize()

        descriptions = []
        for name, tool in self.tools.items():
            desc = f"- {name}: {tool.description if hasattr(tool, 'description') else '无描述'}"
            descriptions.append(desc)

        return "\n".join(descriptions)

    def list_tools(self) -> List[str]:
        """列出所有可用工具名称"""
        if not self._initialized:
            self.initialize()

        return list(self.tools.keys())

    async def _cleanup_async(self):
        """异步清理资源"""
        if not self._initialized:
            return

        # 注意：由于跨事件循环上下文问题，我们只标记为未初始化
        # 实际的资源清理会在 Python 进程退出时自动完成
        logger.info("✅ MCP 连接已标记为关闭")

    def cleanup(self):
        """清理资源"""
        if not self._initialized:
            return

        # 简单标记为未初始化，避免跨事件循环上下文问题
        self._initialized = False
        logger.info("✅ MCP 资源已释放")

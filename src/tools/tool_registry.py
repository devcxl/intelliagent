#!/usr/bin/env python3
"""
工具注册中心

提供内置工具和外部 MCP 工具的统一接口。

架构说明：
  - 内置工具：直接导入 core.builtin_tools 的 Python 函数，无需 MCP 依赖
  - 外部工具：通过 MCP 协议连接的远程服务（可选）
  
连接方式：
  - 内置工具：直接 Python 函数调用
  - MCP 工具：stdio, SSE, streamable-http 三种协议连接
"""
import json
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from utils.logger import logger
from src.config import get_settings

MCP_CONFIG_FILE = get_settings().MCP_CONFIG_FILE

# 导入内置工具
from src.tools.builtin_tools import (
    BUILTIN_TOOLS,
    call_tool as call_builtin_tool
)

# 尝试导入 MCP（可选）
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamablehttp_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    logger.debug("⚠️ MCP 库未安装，仅支持内置工具")


class MCPServer:
    """单个 MCP 服务器连接"""
    
    def __init__(
        self, 
        name: str, 
        command: Optional[str] = None, 
        args: Optional[List[str]] = None, 
        env: Optional[Dict[str, str]] = None,
        server_type: str = "stdio",
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.server_type = server_type  # "stdio" 或 "http"
        
        # stdio 类型参数
        self.command = command
        self.args = args or []
        self.env = env or {}
        
        # http 类型参数
        self.url = url
        self.headers = headers or {}
        
        # 共用属性
        self.session: Optional[ClientSession] = None
        self.tools: Dict[str, Any] = {}
        self.prompts: Dict[str, Any] = {}
        self._context = None
        self.read = None
        self.write = None


class ToolRegistry:
    """MCP 工具注册中心 - 支持多个 MCP 服务器"""

    def __init__(self):
        """初始化 MCP 客户端"""
        self.servers: List[MCPServer] = []
        self.tools: Dict[str, Tuple[MCPServer, Any]] = {}  # tool_name -> (server, tool_info)
        self.prompts: Dict[str, Tuple[MCPServer, Any]] = {}  # prompt_name -> (server, prompt_info)
        self._initialized = False
        logger.info("✅ MCP 资源已释放")

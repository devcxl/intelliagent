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
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from utils.logger import logger
from utils.config import  MCP_CONFIG_FILE

# 导入内置工具
from src.builtin_tools import (
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
        self._loop = None
        logger.info("🔧 MCP 工具注册中心已创建")
        
        # 配置服务器列表
        self._configure_servers()

    def _configure_servers(self):
        """配置 MCP 服务器列表（支持 JSON 配置文件）
        
        注意：内置工具不再通过 MCP 服务器配置。
        它们由 core.builtin_tools 直接提供。
        """
        # 从 JSON 配置文件加载外部 MCP 服务器
        self._load_servers_from_json()

    def _load_servers_from_json(self):
        """从 JSON 配置文件加载 MCP 服务器（支持 stdio 和 http 类型）"""
        config_path = Path(MCP_CONFIG_FILE)
        
        if not config_path.exists():
            logger.debug(f"📄 MCP 配置文件不存在: {MCP_CONFIG_FILE}")
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # 支持 Claude Code 的 mcpServers 格式
            servers_config = config.get('mcpServers', {})
            
            for server_name, server_config in servers_config.items():
                try:
                    # 检测服务器类型
                    server_type = server_config.get('type', 'stdio')
                    
                    if server_type == 'http' or server_type == 'http-streamable' or server_type == 'sse':
                        # HTTP/SSE 类型服务器
                        url = server_config.get('url')
                        headers = server_config.get('headers', {})
                        
                        if not url:
                            logger.warning(f"⚠️ HTTP 服务器 {server_name} 缺少 url 配置")
                            continue
                        
                        # 确保包含必要的 SSE 头
                        if 'Accept' not in headers:
                            headers['Accept'] = 'text/event-stream'
                        
                        # 创建 HTTP 服务器实例
                        mcp_server = MCPServer(
                            name=server_name,
                            server_type='http',
                            url=url,
                            headers=headers
                        )
                        
                        self.servers.append(mcp_server)
                        logger.info(f"✅ 已添加 HTTP MCP 服务器: {server_name} ({url})")
                        
                    else:
                        # stdio 类型服务器
                        command = server_config.get('command')
                        args = server_config.get('args', [])
                        env = server_config.get('env', {})
                        
                        if not command:
                            logger.warning(f"⚠️ 服务器 {server_name} 缺少 command 配置")
                            continue
                        
                        # 创建 stdio 服务器实例
                        mcp_server = MCPServer(
                            name=server_name,
                            command=command,
                            args=args,
                            env=env,
                            server_type='stdio'
                        )
                        
                        self.servers.append(mcp_server)
                        logger.info(f"✅ 已添加 stdio MCP 服务器: {server_name} ({command})")
                    
                except Exception as e:
                    logger.error(f"❌ 加载服务器 {server_name} 失败: {e}")
                    continue
            
            logger.info(f"📦 从配置文件加载了 {len(servers_config)} 个外部 MCP 服务器")
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON 配置文件格式错误: {e}")
        except Exception as e:
            logger.error(f"❌ 读取 MCP 配置文件失败: {e}")

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
        """异步初始化所有 MCP 服务器连接"""
        if self._initialized:
            return

        all_tools = []
        
        for server in self.servers:
            try:
                logger.info(f"🔄 正在连接 MCP 服务器: {server.name} (类型: {server.server_type})")
                
                if server.server_type == 'http':
                    # HTTP streamable 连接（支持 Context7 等服务）
                    server._context = streamablehttp_client(
                        server.url, 
                        headers=server.headers,
                        timeout=10.0,
                        sse_read_timeout=300.0
                    )
                    # streamablehttp_client 返回 (read, write, get_session_id)
                    result = await server._context.__aenter__()
                    server.read, server.write = result[0], result[1]
                    
                else:
                    # stdio 连接
                    # 合并系统环境变量和服务器特定环境变量
                    merged_env = os.environ.copy()
                    if server.env:
                        merged_env.update(server.env)
                    
                    server_params = StdioServerParameters(
                        command=server.command,
                        args=server.args,
                        env=merged_env if server.env else None
                    )

                    # 建立连接
                    server._context = stdio_client(server_params)
                    server.read, server.write = await server._context.__aenter__()

                # 创建会话
                server.session = ClientSession(server.read, server.write)
                await server.session.__aenter__()

                # 初始化会话
                await server.session.initialize()

                # 列出可用工具
                response = await server.session.list_tools()
                server.tools = {tool.name: tool for tool in response.tools}
                
                # 将工具添加到全局工具列表
                for tool_name, tool_info in server.tools.items():
                    if tool_name in self.tools:
                        logger.warning(f"⚠️ 工具名称冲突: {tool_name} (来自 {server.name}，已忽略)")
                    else:
                        self.tools[tool_name] = (server, tool_info)
                        all_tools.append(tool_name)

                # 列出可用 prompts
                try:
                    prompts_response = await server.session.list_prompts()
                    server.prompts = {prompt.name: prompt for prompt in prompts_response.prompts}
                    
                    # 将 prompts 添加到全局列表
                    for prompt_name, prompt_info in server.prompts.items():
                        if prompt_name in self.prompts:
                            logger.warning(f"⚠️ Prompt 名称冲突: {prompt_name} (来自 {server.name}，已忽略)")
                        else:
                            self.prompts[prompt_name] = (server, prompt_info)
                    
                    if server.prompts:
                        logger.info(f"📝 {server.name} 提供 prompts: {list(server.prompts.keys())}")
                except Exception as e:
                    logger.debug(f"服务器 {server.name} 不支持 prompts: {e}")

                logger.info(f"✅ {server.name} 已连接，提供工具: {list(server.tools.keys())}")

            except Exception as e:
                logger.error(f"❌ {server.name} 连接失败: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # 继续尝试其他服务器
                continue

        # 记录初始化结果
        # 注意：即使没有外部 MCP 工具，我们仍然有内置工具可用，所以这不是错误
        if self.tools:
            logger.info(f"✅ MCP 工具注册中心已初始化，总共 {len(self.tools)} 个外部工具: {all_tools}")
        else:
            logger.info(f"✅ 无外部 MCP 工具配置，内置工具已可用")
        
        self._initialized = True

    def initialize(self):
        """同步初始化入口"""
        if self._initialized:
            return

        # 快速路径：如果没有外部 MCP 服务器，直接标记为已初始化
        # 内置工具总是可用的
        if not self.servers:
            logger.debug("⚡ 没有外部 MCP 服务器配置，跳过异步初始化")
            self._initialized = True
            return

        self._loop = self._get_or_create_event_loop()
        self._loop.run_until_complete(self._init_async())

    async def _call_tool_async(self, name: str, arguments: Dict[str, Any]) -> Any:
        """异步调用工具
        
        优先级：
        1. 内置工具（直接 Python 函数调用）
        2. MCP 外部工具（如果已配置）
        """
        # 首先检查是否是内置工具
        if name in BUILTIN_TOOLS:
            logger.debug(f"🔧 调用内置工具: {name}")
            try:
                # 直接调用内置工具
                result_json = await call_builtin_tool(name, **arguments)
                # 解析 JSON 响应
                result = json.loads(result_json)
                return result
            except Exception as e:
                logger.error(f"❌ 调用内置工具 '{name}' 失败: {e}")
                raise
        
        # 否则尝试通过 MCP 调用外部工具
        if not HAS_MCP:
            raise RuntimeError(f"工具 '{name}' 不存在，且 MCP 库未安装")
        
        if not self._initialized:
            await self._init_async()

        if name not in self.tools:
            raise ValueError(f"工具 '{name}' 不存在")

        try:
            # 获取工具所属的服务器
            server, tool_info = self.tools[name]
            
            # 调用对应服务器的工具
            result = await server.session.call_tool(name, arguments)

            # 解析结果
            if result.content:
                content = result.content[0]
                if hasattr(content, 'text'):
                    text = content.text
                    # 尝试解析为 JSON
                    try:
                        response_data = json.loads(text)
                        if response_data.get("status") == "ok":
                            return response_data
                        elif "status" in response_data:
                            raise RuntimeError(response_data.get("error", "未知错误"))
                        else:
                            # 不是标准格式，直接返回
                            return {"status": "ok", "result": response_data}
                    except json.JSONDecodeError:
                        # 不是 JSON，直接返回文本
                        return {"status": "ok", "result": text}

            return {"status": "ok", "result": str(result)}

        except Exception as e:
            logger.error(f"❌ 调用 MCP 工具 '{name}' 失败: {e}")
            raise

    def get_tool(self, name: str):
        """获取工具的包装器"""
        if not self._initialized:
            self.initialize()

        def tool_wrapper(**kwargs):
            """工具调用包装器"""
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    import concurrent.futures
                    import threading
                    
                    result_container = []
                    exception_container = []
                    thread_done = threading.Event()
                    
                    def run_in_new_loop():
                        try:
                            new_loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(new_loop)
                            try:
                                result = new_loop.run_until_complete(
                                    self._call_tool_async(name, kwargs)
                                )
                                result_container.append(result)
                            finally:
                                new_loop.close()
                        except Exception as e:
                            exception_container.append(e)
                        finally:
                            thread_done.set()
                    
                    thread = threading.Thread(target=run_in_new_loop)
                    thread.start()
                    thread_done.wait()
                    
                    if exception_container:
                        raise exception_container[0]
                    if result_container:
                        return result_container[0]
                    raise RuntimeError("工具执行失败：未获取到结果")
            except RuntimeError:
                loop = self._get_or_create_event_loop()
                return loop.run_until_complete(
                    self._call_tool_async(name, kwargs)
                )

        return tool_wrapper

    def describe_tools(self) -> str:
        """描述所有可用工具（包括内置工具）"""
        descriptions = []
        
        # 添加内置工具
        for name, tool_info in BUILTIN_TOOLS.items():
            desc = f"- {name} (内置): {tool_info.get('description', '无描述')}"
            descriptions.append(desc)
        
        # 添加 MCP 外部工具
        if self._initialized or HAS_MCP:
            if not self._initialized:
                self.initialize()
            
            for name, (server, tool) in self.tools.items():
                desc = f"- {name} (from {server.name}): {tool.description if hasattr(tool, 'description') else '无描述'}"
                descriptions.append(desc)

        return "\n".join(descriptions)

    def list_tools(self) -> List[str]:
        """列出所有可用工具名称（包括内置工具）"""
        tools = list(BUILTIN_TOOLS.keys())
        
        if self._initialized or HAS_MCP:
            if not self._initialized:
                self.initialize()
            
            tools.extend(list(self.tools.keys()))
        
        return tools

    async def _get_prompt_async(self, name: str, arguments: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """异步获取 prompt"""
        if not self._initialized:
            await self._init_async()

        if name not in self.prompts:
            raise ValueError(f"Prompt '{name}' 不存在")

        try:
            # 获取 prompt 所属的服务器
            server, prompt_info = self.prompts[name]
            
            # 调用对应服务器的 get_prompt
            result = await server.session.get_prompt(name, arguments)

            # 返回 prompt 的消息
            return {
                "status": "ok",
                "description": result.description if hasattr(result, 'description') else None,
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content.model_dump() if hasattr(msg.content, 'model_dump') else str(msg.content)
                    }
                    for msg in result.messages
                ]
            }

        except Exception as e:
            logger.error(f"❌ 获取 prompt '{name}' 失败: {e}")
            raise

    def get_prompt(self, name: str, arguments: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """获取 prompt（同步接口）"""
        if not self._initialized:
            self.initialize()

        loop = self._get_or_create_event_loop()
        return loop.run_until_complete(
            self._get_prompt_async(name, arguments)
        )

    def list_prompts(self) -> List[str]:
        """列出所有可用的 prompts"""
        if not self._initialized:
            self.initialize()

        return list(self.prompts.keys())

    def describe_prompts(self) -> str:
        """描述所有可用 prompts"""
        if not self._initialized:
            self.initialize()

        descriptions = []
        for name, (server, prompt) in self.prompts.items():
            desc = f"- {name} (from {server.name}): {prompt.description if hasattr(prompt, 'description') else '无描述'}"
            if hasattr(prompt, 'arguments') and prompt.arguments:
                args_desc = ", ".join([f"{arg.name}{'*' if arg.required else ''}" for arg in prompt.arguments])
                desc += f"\n  参数: {args_desc}"
            descriptions.append(desc)

        return "\n".join(descriptions)

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


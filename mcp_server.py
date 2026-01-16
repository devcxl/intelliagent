#!/usr/bin/env python3
"""
MCP 工具服务器（可选）

将内置工具暴露为 MCP 服务，用于与其他 MCP 客户端集成。
注意：这是可选的包装层，内置工具本身独立于 MCP。

如果不需要 MCP 暴露，可以直接从 core.builtin_tools 导入使用内置工具。
"""

from mcp.server.fastmcp import FastMCP
from core.builtin_tools import (
    run_shell,
    read_file,
    write_file,
    list_dir,
    delete_file,
    file_exists
)

# 创建 FastMCP 服务器实例
mcp = FastMCP("intelliagent-tools")


# 暴露内置工具为 MCP 服务
@mcp.tool()
async def mcp_run_shell(cmd: str) -> str:
    """执行终端命令 (MCP 包装)"""
    return await run_shell(cmd)


@mcp.tool()
async def mcp_read_file(path: str) -> str:
    """读取文件内容 (MCP 包装)"""
    return await read_file(path)


@mcp.tool()
async def mcp_write_file(path: str, content: str) -> str:
    """写入文件内容 (MCP 包装)"""
    return await write_file(path, content)


@mcp.tool()
async def mcp_list_dir(path: str = ".") -> str:
    """列出目录内容 (MCP 包装)"""
    return await list_dir(path)


@mcp.tool()
async def mcp_delete_file(path: str) -> str:
    """删除文件 (MCP 包装)"""
    return await delete_file(path)


@mcp.tool()
async def mcp_file_exists(path: str) -> str:
    """检查文件/目录是否存在 (MCP 包装)"""
    return await file_exists(path)


if __name__ == "__main__":
    mcp.run(transport='stdio')

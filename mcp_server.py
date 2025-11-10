#!/usr/bin/env python3
"""
MCP 工具服务器
提供 shell、文件、测试、git 等工具的 MCP 接口
"""
import asyncio
import json
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP

# 尝试导入 aiofiles
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

# 创建 FastMCP 服务器实例
mcp = FastMCP("intelliagent-tools")


def success_response(data: Dict[str, Any]) -> str:
    """创建成功响应"""
    return json.dumps({"status": "ok", **data}, ensure_ascii=False)


def error_response(error: str) -> str:
    """创建错误响应"""
    return json.dumps({"status": "error", "error": error}, ensure_ascii=False)


@mcp.tool()
async def run_shell(cmd: str) -> str:
    """执行终端命令

    Args:
        cmd: 要执行的命令
    """
    if not cmd:
        return error_response("缺少 cmd 参数")

    try:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode() if stdout else stderr.decode()

        return success_response({"output": output.strip()})
    except Exception as e:
        return error_response(str(e))



@mcp.tool()
async def read_file(path: str) -> str:
    """读取文件内容

    Args:
        path: 文件路径
    """
    if not path:
        return error_response("缺少 path 参数")

    try:
        # 使用异步文件读取
        if HAS_AIOFILES:
            async with aiofiles.open(path, "r", encoding="utf-8") as f:
                content = await f.read()
        else:
            # 如果没有 aiofiles，使用同步方式
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

        # 限制返回内容长度，避免过大响应
        max_length = 5000
        if len(content) > max_length:
            content = content[:max_length] + f"\n...(已截断，总长度: {len(content)})"

        return success_response({"content": content})
    except Exception as e:
        return error_response(str(e))



@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """写入文件内容

    Args:
        path: 文件路径
        content: 文件内容
    """
    if not path:
        return error_response("缺少 path 参数")
    if content is None:
        return error_response("缺少 content 参数")

    try:
        # 使用异步文件写入
        if HAS_AIOFILES:
            async with aiofiles.open(path, "w", encoding="utf-8") as f:
                await f.write(content)
        else:
            # 如果没有 aiofiles，使用同步方式
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

        return success_response({"message": f"文件已写入: {path}"})
    except Exception as e:
        return error_response(str(e))



@mcp.tool()
async def run_tests(test_path: str = ".") -> str:
    """运行测试

    Args:
        test_path: 测试文件或目录路径，默认为当前目录
    """
    try:
        # 运行 pytest
        cmd = f"pytest {test_path} -v"
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode() if stdout else stderr.decode()

        return success_response({
            "output": output,
            "exit_code": process.returncode
        })
    except Exception as e:
        return error_response(str(e))



@mcp.tool()
async def git_commit(message: str) -> str:
    """Git提交代码

    Args:
        message: 提交信息
    """
    if not message:
        return error_response("缺少 message 参数")

    try:
        # 先 add 所有更改
        process = await asyncio.create_subprocess_shell(
            "git add .",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        # 执行提交
        cmd = f'git commit -m "{message}"'
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        output = stdout.decode() if stdout else stderr.decode()

        return success_response({"output": output.strip()})
    except Exception as e:
        return error_response(str(e))


if __name__ == "__main__":
    # 运行服务器
    mcp.run(transport='stdio')



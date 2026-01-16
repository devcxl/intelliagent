#!/usr/bin/env python3
"""
MCP 工具服务器
提供 shell、文件、目录等工具的 MCP 接口
"""
import asyncio
import json
import os
import pathlib
from typing import Dict, Any, List
from mcp.server.fastmcp import FastMCP

# 尝试导入 aiofiles
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

# 创建 FastMCP 服务器实例
mcp = FastMCP("intelliagent-tools")

# 工具配置常量
SHELL_COMMAND_TIMEOUT = 30  # 秒
FILE_READ_MAX_SIZE = 50000  # 字符数
FILE_WRITE_MAX_SIZE = 1000000  # 字符数（1MB）
DIR_LIST_MAX_ITEMS = 1000  # 目录列表最多返回项数


def success_response(data: Dict[str, Any]) -> str:
    """创建成功响应
    
    Args:
        data: 响应数据字典
        
    Returns:
        JSON 格式的成功响应
    """
    return json.dumps({"status": "ok", **data}, ensure_ascii=False)


def error_response(error: str, code: str = "UNKNOWN_ERROR") -> str:
    """创建错误响应
    
    Args:
        error: 错误描述
        code: 错误代码
        
    Returns:
        JSON 格式的错误响应
    """
    return json.dumps({"status": "error", "error": error, "code": code}, ensure_ascii=False)


@mcp.tool()
async def run_shell(cmd: str) -> str:
    """执行终端命令
    
    执行系统 shell 命令并返回输出结果。
    支持管道、重定向等标准 shell 语法。

    Args:
        cmd: 要执行的 shell 命令（字符串）
        
    Returns:
        {"status": "ok", "output": "命令输出", "returncode": 0}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_COMMAND: 命令为空
        - TIMEOUT: 命令执行超时（>30秒）
        - EXECUTION_ERROR: 命令执行失败
        
    Examples:
        - run_shell("ls -la /tmp")
        - run_shell("echo 'Hello' > /tmp/test.txt")
        - run_shell("python -c 'print(1+1)'")
    """
    # 参数验证
    if not cmd or not isinstance(cmd, str):
        return error_response("cmd 参数为空或非字符串类型", "EMPTY_COMMAND")

    cmd = cmd.strip()
    if not cmd:
        return error_response("cmd 参数为空或仅包含空格", "EMPTY_COMMAND")

    try:
        # 使用超时创建子进程
        process = await asyncio.wait_for(
            asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            ),
            timeout=SHELL_COMMAND_TIMEOUT
        )
        
        # 等待进程完成，带超时
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=SHELL_COMMAND_TIMEOUT
        )
        
        # 返回标准输出（优先），如果为空则返回标准错误
        output = stdout.decode('utf-8', errors='replace') if stdout else stderr.decode('utf-8', errors='replace')
        
        return success_response({
            "output": output.strip(),
            "returncode": process.returncode
        })
        
    except asyncio.TimeoutError:
        return error_response(
            f"命令执行超时（超过 {SHELL_COMMAND_TIMEOUT} 秒）",
            "TIMEOUT"
        )
    except Exception as e:
        return error_response(
            f"命令执行失败: {str(e)}",
            "EXECUTION_ERROR"
        )


@mcp.tool()
async def read_file(path: str) -> str:
    """读取文件内容
    
    读取指定路径的文件内容。支持文本文件，返回内容和文件信息。
    大文件会被截断并标记。

    Args:
        path: 文件路径（绝对路径或相对路径）
        
    Returns:
        {"status": "ok", "content": "文件内容", "size": 1024, "truncated": false}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - FILE_NOT_FOUND: 文件不存在
        - IS_DIRECTORY: 目标是目录而非文件
        - PERMISSION_DENIED: 无读取权限
        - FILE_TOO_LARGE: 文件大小超出限制 (>50000 字符)
        - READ_ERROR: 读取失败
        
    Examples:
        - read_file("README.md")
        - read_file("/etc/hosts")
        - read_file("./src/main.py")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    try:
        # 规范化路径
        file_path = pathlib.Path(path).resolve()
        
        # 检查文件是否存在
        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")
        
        # 检查是否是目录
        if file_path.is_dir():
            return error_response(f"目标是目录而非文件: {path}", "IS_DIRECTORY")
        
        # 获取文件大小
        file_size = file_path.stat().st_size
        
        # 使用异步文件读取
        if HAS_AIOFILES:
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = await f.read()
        else:
            # 如果没有 aiofiles，使用同步方式
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        
        # 检查内容长度，超出限制则截断
        truncated = False
        if len(content) > FILE_READ_MAX_SIZE:
            content = content[:FILE_READ_MAX_SIZE] + f"\n\n[文件已截断，原文件大小: {len(content)} 字符]"
            truncated = True
        
        return success_response({
            "content": content,
            "size": len(content),
            "file_size": file_size,
            "truncated": truncated
        })
        
    except PermissionError:
        return error_response(f"无读取权限: {path}", "PERMISSION_DENIED")
    except Exception as e:
        return error_response(f"读取文件失败: {str(e)}", "READ_ERROR")


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """写入文件内容
    
    将内容写入指定路径的文件。如果文件不存在则创建，存在则覆盖。
    自动创建父目录。

    Args:
        path: 文件路径（绝对路径或相对路径）
        content: 要写入的文件内容
        
    Returns:
        {"status": "ok", "message": "文件已写入", "path": "/abs/path", "size": 1024}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - EMPTY_CONTENT: 内容为空
        - CONTENT_TOO_LARGE: 内容大小超出限制 (>1MB)
        - PERMISSION_DENIED: 无写入权限
        - INVALID_PATH: 路径无效或被用作目录
        - WRITE_ERROR: 写入失败
        
    Examples:
        - write_file("test.txt", "Hello World")
        - write_file("/tmp/output.json", '{"key": "value"}')
        - write_file("./src/config.py", "CONFIG = {}")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    if content is None:
        return error_response("content 参数为空", "EMPTY_CONTENT")
    
    if not isinstance(content, str):
        return error_response("content 参数非字符串类型", "EMPTY_CONTENT")
    
    # 检查内容大小
    if len(content) > FILE_WRITE_MAX_SIZE:
        return error_response(
            f"文件内容过大（{len(content)} 字符，限制 {FILE_WRITE_MAX_SIZE}）",
            "CONTENT_TOO_LARGE"
        )
    
    try:
        # 规范化路径
        file_path = pathlib.Path(path).resolve()
        
        # 检查是否有文件与目录同名的问题
        if file_path.exists() and file_path.is_dir():
            return error_response(f"目标已存在且为目录: {path}", "INVALID_PATH")
        
        # 创建父目录（如不存在）
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用异步文件写入
        if HAS_AIOFILES:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)
        else:
            # 如果没有 aiofiles，使用同步方式
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        
        return success_response({
            "message": f"文件已写入: {file_path.name}",
            "path": str(file_path),
            "size": len(content)
        })
        
    except PermissionError:
        return error_response(f"无写入权限: {path}", "PERMISSION_DENIED")
    except Exception as e:
        return error_response(f"写入文件失败: {str(e)}", "WRITE_ERROR")


@mcp.tool()
async def list_dir(path: str = ".") -> str:
    """列出目录内容
    
    列出指定目录中的文件和子目录。可按类型、名称、大小等条件筛选。

    Args:
        path: 目录路径，默认为当前目录 "."
        
    Returns:
        {"status": "ok", "items": [...], "count": 42, "directory": "/abs/path"}
        items 中每个对象包含:
        {
            "name": "filename.txt",
            "type": "file|directory",
            "size": 1024
        }
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - NOT_FOUND: 目录不存在
        - NOT_A_DIRECTORY: 路径指向文件而非目录
        - PERMISSION_DENIED: 无读取权限
        - LIST_ERROR: 列表操作失败
        
    Examples:
        - list_dir(".")
        - list_dir("/tmp")
        - list_dir("src/")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        path = "."
    
    path = path.strip()
    if not path:
        path = "."
    
    try:
        # 规范化路径
        dir_path = pathlib.Path(path).resolve()
        
        # 检查路径是否存在
        if not dir_path.exists():
            return error_response(f"目录不存在: {path}", "NOT_FOUND")
        
        # 检查是否是目录
        if not dir_path.is_dir():
            return error_response(f"路径指向文件而非目录: {path}", "NOT_A_DIRECTORY")
        
        # 列出目录内容
        items = []
        try:
            entries = sorted(dir_path.iterdir(), key=lambda x: x.name)
            for entry in entries[:DIR_LIST_MAX_ITEMS]:
                item_info = {
                    "name": entry.name,
                    "type": "directory" if entry.is_dir() else "file"
                }
                
                # 添加大小信息
                if not entry.is_dir():
                    try:
                        item_info["size"] = entry.stat().st_size
                    except OSError:
                        item_info["size"] = 0
                
                items.append(item_info)
        except PermissionError:
            return error_response(f"无读取权限: {path}", "PERMISSION_DENIED")
        
        return success_response({
            "items": items,
            "count": len(items),
            "directory": str(dir_path),
            "truncated": len(entries) > DIR_LIST_MAX_ITEMS
        })
        
    except PermissionError:
        return error_response(f"无读取权限: {path}", "PERMISSION_DENIED")
    except Exception as e:
        return error_response(f"列表目录失败: {str(e)}", "LIST_ERROR")


@mcp.tool()
async def delete_file(path: str) -> str:
    """删除文件
    
    删除指定路径的文件。仅支持删除文件，不支持删除目录。

    Args:
        path: 文件路径
        
    Returns:
        {"status": "ok", "message": "文件已删除", "path": "/abs/path"}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - NOT_FOUND: 文件不存在
        - IS_DIRECTORY: 目标是目录而非文件
        - PERMISSION_DENIED: 无删除权限
        - DELETE_ERROR: 删除失败
        
    Examples:
        - delete_file("temp.txt")
        - delete_file("/tmp/cache.json")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    try:
        # 规范化路径
        file_path = pathlib.Path(path).resolve()
        
        # 检查文件是否存在
        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "NOT_FOUND")
        
        # 检查是否是目录
        if file_path.is_dir():
            return error_response(f"目标是目录而非文件（禁止删除目录）: {path}", "IS_DIRECTORY")
        
        # 删除文件
        file_path.unlink()
        
        return success_response({
            "message": f"文件已删除: {file_path.name}",
            "path": str(file_path)
        })
        
    except PermissionError:
        return error_response(f"无删除权限: {path}", "PERMISSION_DENIED")
    except Exception as e:
        return error_response(f"删除文件失败: {str(e)}", "DELETE_ERROR")


@mcp.tool()
async def file_exists(path: str) -> str:
    """检查文件或目录是否存在
    
    检查指定路径是否存在，并返回类型信息。

    Args:
        path: 文件或目录路径
        
    Returns:
        {"status": "ok", "exists": true, "type": "file|directory"}
        {"status": "ok", "exists": false}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Examples:
        - file_exists("README.md")
        - file_exists("/tmp")
        - file_exists("./nonexistent.txt")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    try:
        # 规范化路径
        target_path = pathlib.Path(path).resolve()
        
        # 检查是否存在
        if target_path.exists():
            return success_response({
                "exists": True,
                "type": "directory" if target_path.is_dir() else "file"
            })
        else:
            return success_response({
                "exists": False
            })
        
    except Exception as e:
        return error_response(f"检查文件失败: {str(e)}", "CHECK_ERROR")


if __name__ == "__main__":
    # 运行服务器
    mcp.run(transport='stdio')

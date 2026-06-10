#!/usr/bin/env python3
"""
内置工具模块 - 纯 Python 实现

提供 IntelliAgent 的 7 个内置工具，无需 MCP 依赖。
这些工具可以直接在项目内部使用，也可以通过 MCP 暴露给外部。

工具列表：
  1. run_shell - 执行终端命令
  2. read_file - 读取文件内容
  3. write_file - 写入文件内容
  4. edit_file - 编辑文件内容（精确替换）
  5. list_dir - 列出目录内容
  6. delete_file - 删除文件
  7. file_exists - 检查文件/目录存在性
"""

import asyncio
import json
import os
import pathlib
import shutil
from typing import Dict, Any, List

# 尝试导入 aiofiles（可选，用于异步文件操作）
try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

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
        # 优先使用 bash，保证管道和转义行为更稳定；缺失时再回退到默认 shell
        bash_path = shutil.which("bash")
        if bash_path:
            process = await asyncio.create_subprocess_exec(
                bash_path,
                "-lc",
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=SHELL_COMMAND_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            return error_response(
                f"命令执行超时（>{SHELL_COMMAND_TIMEOUT}秒）",
                "TIMEOUT"
            )
        
        # 解码输出
        output = stdout.decode('utf-8', errors='replace').strip()
        error_output = stderr.decode('utf-8', errors='replace').strip()
        
        # 组合输出
        full_output = output
        if error_output and process.returncode != 0:
            full_output = f"{output}\n{error_output}".strip()
        
        return success_response({
            "output": full_output,
            "returncode": process.returncode
        })
        
    except Exception as e:
        return error_response(f"命令执行失败: {str(e)}", "EXECUTION_ERROR")


async def read_file(path: str) -> str:
    """读取文件内容
    
    读取指定文件的内容，支持文本文件。
    超过 50KB 的文件会被截断。

    Args:
        path: 文件路径
        
    Returns:
        {"status": "ok", "content": "...", "size": 1024, "truncated": false}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - FILE_NOT_FOUND: 文件不存在
        - IS_DIRECTORY: 路径是目录而非文件
        - READ_ERROR: 读取失败
        - CONTENT_TOO_LARGE: 内容超过大小限制
        
    Examples:
        - read_file("README.md")
        - read_file("/etc/hosts")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    try:
        file_path = pathlib.Path(path).expanduser()
        
        # 检查路径是否存在
        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")
        
        # 检查是否是目录
        if file_path.is_dir():
            return error_response(f"路径是目录而非文件: {path}", "IS_DIRECTORY")
        
        # 读取文件
        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
        else:
            content = file_path.read_text(encoding='utf-8')
        
        # 检查大小限制
        truncated = False
        if len(content) > FILE_READ_MAX_SIZE:
            content = content[:FILE_READ_MAX_SIZE]
            truncated = True
        
        return success_response({
            "content": content,
            "size": len(content),
            "truncated": truncated,
            "path": str(file_path)
        })
        
    except Exception as e:
        return error_response(f"读取文件失败: {str(e)}", "READ_ERROR")


async def write_file(path: str, content: str) -> str:
    """写入文件内容
    
    创建或覆盖指定路径的文件。自动创建不存在的父目录。
    文件大小限制为 1MB。

    Args:
        path: 文件路径
        content: 文件内容
        
    Returns:
        {"status": "ok", "message": "文件已创建", "path": "...", "size": 1024}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - EMPTY_CONTENT: 内容为空
        - CONTENT_TOO_LARGE: 内容超过 1MB 限制
        - WRITE_ERROR: 写入失败
        - NOT_A_DIRECTORY: 父路径不是目录
        
    Examples:
        - write_file("/tmp/test.txt", "Hello World")
        - write_file("output/result.json", json_content)
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
        content = str(content)
    
    # 检查内容大小限制
    if len(content) > FILE_WRITE_MAX_SIZE:
        return error_response(
            f"内容过大（{len(content)} > {FILE_WRITE_MAX_SIZE} 字符），超过 1MB 限制",
            "CONTENT_TOO_LARGE"
        )
    
    try:
        file_path = pathlib.Path(path).expanduser()
        
        # 创建父目录
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
                await f.write(content)
        else:
            file_path.write_text(content, encoding='utf-8')
        
        return success_response({
            "message": "文件已创建",
            "path": str(file_path),
            "size": len(content)
        })
        
    except Exception as e:
        return error_response(f"写入文件失败: {str(e)}", "WRITE_ERROR")


async def edit_file(path: str, oldString: str, newString: str, replaceAll: bool = False) -> str:
    """编辑文件内容（类似 git patch 的精确替换）
    
    在文件中精确查找并替换指定的文本片段。
    支持 单次替换或全局替换模式。

    Args:
        path: 文件路径
        oldString: 要替换的旧字符串
        newString: 新字符串
        replaceAll: 是否替换所有匹配项（默认 false，仅替换第一个）
        
    Returns:
        {"status": "ok", "replacements": 1, "content": "...", "path": "..."}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - EMPTY_OLD_STRING: oldString 为空
        - FILE_NOT_FOUND: 文件不存在
        - IS_DIRECTORY: 路径是目录而非文件
        - OLD_STRING_NOT_FOUND: oldString 在文件中未找到
        - MULTIPLE_MATCHES: 找到多个匹配但 replaceAll=false
        - WRITE_ERROR: 写入失败
        
    Examples:
        - edit_file("test.txt", "Hello", "Hi")
        - edit_file("test.py", "old_function", "new_function", replaceAll=True)
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    if not oldString or not isinstance(oldString, str):
        return error_response("oldString 参数为空或非字符串类型", "EMPTY_OLD_STRING")
    
    oldString = oldString.strip()
    if not oldString:
        return error_response("oldString 参数为空或仅包含空格", "EMPTY_OLD_STRING")
    
    if newString is None:
        newString = ""
    
    try:
        file_path = pathlib.Path(path).expanduser()
        
        # 检查文件是否存在
        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")
        
        # 检查是否是目录
        if file_path.is_dir():
            return error_response(f"路径是目录而非文件: {path}", "IS_DIRECTORY")
        
        # 读取文件内容
        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
        else:
            content = file_path.read_text(encoding='utf-8')
        
        # 查找 oldString 的出现次数
        occurrence_count = content.count(oldString)
        
        if occurrence_count == 0:
            return error_response(
                f"未找到要替换的文本片段，请检查 oldString 是否正确",
                "OLD_STRING_NOT_FOUND"
            )
        
        # 如果有多个匹配但 replaceAll=False
        if occurrence_count > 1 and not replaceAll:
            return error_response(
                f"找到 {occurrence_count} 处匹配，但 replaceAll=False，仅允许单次替换。请设置 replaceAll=True 或提供更精确的 oldString。",
                "MULTIPLE_MATCHES"
            )
        
        # 执行替换
        if replaceAll:
            new_content = content.replace(oldString, newString)
        else:
            new_content = content.replace(oldString, newString, 1)
        
        # 检查内容大小限制
        if len(new_content) > FILE_WRITE_MAX_SIZE:
            return error_response(
                f"编辑后内容过大（{len(new_content)} > {FILE_WRITE_MAX_SIZE} 字符），超过 1MB 限制",
                "CONTENT_TOO_LARGE"
            )
        
        # 写回文件
        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
                await f.write(new_content)
        else:
            file_path.write_text(new_content, encoding='utf-8')
        
        # 返回替换结果（最多返回 500 字符的内容片段）
        preview_length = 500
        content_preview = new_content[:preview_length]
        if len(new_content) > preview_length:
            content_preview += "..."
        
        return success_response({
            "message": "文件编辑成功",
            "replacements": occurrence_count if replaceAll else 1,
            "content": content_preview,
            "path": str(file_path),
            "size": len(new_content)
        })
        
    except Exception as e:
        return error_response(f"编辑文件失败: {str(e)}", "WRITE_ERROR")


async def list_dir(path: str = ".") -> str:
    """列出目录内容
    
    列出指定目录下的文件和子目录。
    最多返回 1000 个项目。

    Args:
        path: 目录路径（默认当前目录）
        
    Returns:
        {
            "status": "ok",
            "items": [
                {"name": "file.txt", "type": "file", "size": 1024},
                {"name": "dir", "type": "directory"}
            ],
            "count": 5,
            "directory": "..."
        }
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - NOT_FOUND: 目录不存在
        - NOT_A_DIRECTORY: 路径不是目录
        - LIST_ERROR: 列表失败
        
    Examples:
        - list_dir(".")
        - list_dir("/tmp")
        - list_dir("src")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        path = "."
    
    try:
        dir_path = pathlib.Path(path).expanduser()
        
        # 检查目录是否存在
        if not dir_path.exists():
            return error_response(f"目录不存在: {path}", "NOT_FOUND")
        
        # 检查是否是目录
        if not dir_path.is_dir():
            return error_response(f"路径不是目录: {path}", "NOT_A_DIRECTORY")
        
        # 列出目录内容
        items = []
        for entry in dir_path.iterdir():
            if len(items) >= DIR_LIST_MAX_ITEMS:
                break
            
            item = {
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file"
            }
            
            # 对于文件，添加大小信息
            if entry.is_file():
                try:
                    item["size"] = entry.stat().st_size
                except:
                    pass
            
            items.append(item)
        
        # 按名称排序
        items.sort(key=lambda x: x["name"])
        
        return success_response({
            "items": items,
            "count": len(items),
            "directory": str(dir_path.resolve()),
            "limited": len(items) >= DIR_LIST_MAX_ITEMS
        })
        
    except Exception as e:
        return error_response(f"列表目录失败: {str(e)}", "LIST_ERROR")


async def delete_file(path: str) -> str:
    """删除文件
    
    删除指定的文件。不支持删除目录。

    Args:
        path: 文件路径
        
    Returns:
        {"status": "ok", "message": "文件已删除", "path": "..."}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - FILE_NOT_FOUND: 文件不存在
        - IS_DIRECTORY: 路径是目录而非文件
        - DELETE_ERROR: 删除失败
        - PERMISSION_DENIED: 权限不足
        
    Examples:
        - delete_file("/tmp/test.txt")
        - delete_file("output/temp.log")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    try:
        file_path = pathlib.Path(path).expanduser()
        
        # 检查文件是否存在
        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")
        
        # 检查是否是目录
        if file_path.is_dir():
            return error_response(f"路径是目录，不支持删除目录: {path}", "IS_DIRECTORY")
        
        # 删除文件
        file_path.unlink()
        
        return success_response({
            "message": "文件已删除",
            "path": str(file_path)
        })
        
    except PermissionError:
        return error_response(f"权限不足，无法删除文件: {path}", "PERMISSION_DENIED")
    except Exception as e:
        return error_response(f"删除文件失败: {str(e)}", "DELETE_ERROR")


async def file_exists(path: str) -> str:
    """检查文件/目录是否存在
    
    检查指定路径是否存在，并返回其类型。

    Args:
        path: 文件或目录路径
        
    Returns:
        {"status": "ok", "exists": true, "type": "file"}
        {"status": "ok", "exists": false}
        {"status": "error", "error": "错误描述", "code": "ERROR_CODE"}
        
    Raises:
        - EMPTY_PATH: 路径为空
        - CHECK_ERROR: 检查失败
        
    Examples:
        - file_exists("README.md")
        - file_exists("/tmp")
        - file_exists("nonexistent.txt")
    """
    # 参数验证
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    
    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    
    try:
        file_path = pathlib.Path(path).expanduser()
        
        # 检查是否存在
        if file_path.exists():
            # 返回类型
            file_type = "directory" if file_path.is_dir() else "file"
            return success_response({
                "exists": True,
                "type": file_type,
                "path": str(file_path.resolve())
            })
        else:
            return success_response({
                "exists": False
            })
        
    except Exception as e:
        return error_response(f"检查文件失败: {str(e)}", "CHECK_ERROR")


# 工具注册表（便于统一管理）
BUILTIN_TOOLS = {
    "run_shell": {
        "name": "run_shell",
        "description": "执行终端命令",
        "function": run_shell,
        "parameters": {
            "cmd": {
                "type": "string",
                "description": "要执行的 shell 命令",
                "required": True
            }
        }
    },
    "read_file": {
        "name": "read_file",
        "description": "读取文件内容",
        "function": read_file,
        "parameters": {
            "path": {
                "type": "string",
                "description": "文件路径",
                "required": True
            }
        }
    },
    "write_file": {
        "name": "write_file",
        "description": "写入文件内容",
        "function": write_file,
        "parameters": {
            "path": {
                "type": "string",
                "description": "文件路径",
                "required": True
            },
            "content": {
                "type": "string",
                "description": "文件内容",
                "required": True
            }
        }
    },
    "edit_file": {
        "name": "edit_file",
        "description": "编辑文件内容（精确替换旧字符串为新字符串）",
        "function": edit_file,
        "parameters": {
            "path": {
                "type": "string",
                "description": "文件路径",
                "required": True
            },
            "oldString": {
                "type": "string",
                "description": "要替换的旧字符串",
                "required": True
            },
            "newString": {
                "type": "string",
                "description": "新字符串",
                "required": True
            },
            "replaceAll": {
                "type": "boolean",
                "description": "是否替换所有匹配项（默认 false）",
                "required": False,
                "default": False
            }
        }
    },
    "list_dir": {
        "name": "list_dir",
        "description": "列出目录内容",
        "function": list_dir,
        "parameters": {
            "path": {
                "type": "string",
                "description": "目录路径",
                "required": False,
                "default": "."
            }
        }
    },
    "delete_file": {
        "name": "delete_file",
        "description": "删除文件",
        "function": delete_file,
        "parameters": {
            "path": {
                "type": "string",
                "description": "文件路径",
                "required": True
            }
        }
    },
    "file_exists": {
        "name": "file_exists",
        "description": "检查文件/目录是否存在",
        "function": file_exists,
        "parameters": {
            "path": {
                "type": "string",
                "description": "文件或目录路径",
                "required": True
            }
        }
    }
}


async def call_tool(name: str, **kwargs) -> str:
    """调用内置工具的统一接口
    
    Args:
        name: 工具名称
        **kwargs: 工具参数
        
    Returns:
        JSON 字符串格式的结果
        
    Examples:
        result = await call_tool("read_file", path="README.md")
        result = await call_tool("run_shell", cmd="ls -la")
    """
    if name not in BUILTIN_TOOLS:
        return error_response(f"未知工具: {name}", "UNKNOWN_TOOL")
    
    tool = BUILTIN_TOOLS[name]
    try:
        return await tool["function"](**kwargs)
    except TypeError as e:
        return error_response(f"工具参数错误: {str(e)}", "INVALID_PARAMETERS")
    except Exception as e:
        return error_response(f"工具执行失败: {str(e)}", "EXECUTION_ERROR")


if __name__ == "__main__":
    # 简单的测试
    async def test():
        # 测试 run_shell
        result = await run_shell("echo 'Hello from builtin tools!'")
        print(f"run_shell: {result}")
        
        # 测试 write_file
        result = await write_file("/tmp/test_builtin.txt", "Test content")
        print(f"write_file: {result}")
        
        # 测试 read_file
        result = await read_file("/tmp/test_builtin.txt")
        print(f"read_file: {result}")
        
        # 测试 edit_file
        result = await edit_file("/tmp/test_builtin.txt", "Test content", "Edited content")
        print(f"edit_file: {result}")
        
        # 测试 file_exists
        result = await file_exists("/tmp/test_builtin.txt")
        print(f"file_exists: {result}")
        
        # 测试 delete_file
        result = await delete_file("/tmp/test_builtin.txt")
        print(f"delete_file: {result}")
    
    asyncio.run(test())

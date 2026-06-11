from __future__ import annotations

import json
from typing import Any, Callable, Coroutine

from .shell_tool import run_shell
from .file_tools import read_file, write_file, edit_file
from .response import error_response, success_response

ToolFn = Callable[..., Coroutine[Any, Any, str]]


def _param_schema(param_type: str, description: str, required: bool = False) -> dict[str, Any]:
    return {"type": param_type, "description": description}


def _to_openai_function(name: str, description: str, params: dict[str, dict[str, Any]]) -> dict[str, Any]:
    properties = {}
    required: list[str] = []
    for pname, pinfo in params.items():
        properties[pname] = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
        }
        if pinfo.get("required"):
            required.append(pname)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


async def _todo_write(todos: str) -> str:
    try:
        items = json.loads(todos)
        if not isinstance(items, list):
            return error_response("todos 必须是 JSON 数组", "INVALID_PARAMETERS")
        return success_response({"todos": items, "count": len(items)})
    except json.JSONDecodeError as e:
        return error_response(f"todos JSON 解析失败: {e}", "INVALID_PARAMETERS")


BUILTIN_TOOLS: dict[str, dict[str, Any]] = {
    "run_shell": {
        "name": "run_shell",
        "description": "执行终端命令",
        "function": run_shell,
        "parameters": {
            "cmd": {"type": "string", "description": "要执行的 shell 命令", "required": True}
        },
    },
    "read_file": {
        "name": "read_file",
        "description": "读取文件内容",
        "function": read_file,
        "parameters": {
            "path": {"type": "string", "description": "文件路径", "required": True}
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "写入文件内容",
        "function": write_file,
        "parameters": {
            "path": {"type": "string", "description": "文件路径", "required": True},
            "content": {"type": "string", "description": "文件内容", "required": True},
        },
    },
    "edit_file": {
        "name": "edit_file",
        "description": "编辑文件内容（精确替换旧字符串为新字符串）",
        "function": edit_file,
        "parameters": {
            "path": {"type": "string", "description": "文件路径", "required": True},
            "oldString": {"type": "string", "description": "要替换的旧字符串", "required": True},
            "newString": {"type": "string", "description": "新字符串", "required": True},
            "replaceAll": {"type": "boolean", "description": "是否替换所有匹配项（默认 false）", "required": False},
        },
    },
    "todo_write": {
        "name": "todo_write",
        "description": "创建和更新结构化任务列表，用于跟踪多步骤工作的进度",
        "function": _todo_write,
        "parameters": {
            "todos": {
                "type": "string",
                "description": "JSON 字符串，任务数组，每项含 content/status/priority 字段",
                "required": True,
            },
        },
    },
}


def get_openai_tools() -> list[dict[str, Any]]:
    return [
        _to_openai_function(t["name"], t["description"], t["parameters"])
        for t in BUILTIN_TOOLS.values()
    ]


def get_tool_fn(name: str) -> ToolFn | None:
    tool = BUILTIN_TOOLS.get(name)
    return tool["function"] if tool else None


def list_tool_names() -> list[str]:
    return list(BUILTIN_TOOLS.keys())


async def call_tool(name: str, **kwargs) -> str:
    if name not in BUILTIN_TOOLS:
        return error_response(f"未知工具: {name}", "UNKNOWN_TOOL")

    tool = BUILTIN_TOOLS[name]
    try:
        return await tool["function"](**kwargs)
    except TypeError as e:
        return error_response(f"工具参数错误: {str(e)}", "INVALID_PARAMETERS")
    except Exception as e:
        return error_response(f"工具执行失败: {str(e)}", "EXECUTION_ERROR")

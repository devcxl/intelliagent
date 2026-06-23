from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from src.utils.logger import logger

from .file_tools import edit_file, read_file, write_file
from .response import error_response, success_response
from .shell_tool import run_shell

ToolFn = Callable[..., Coroutine[Any, Any, str]]


@dataclass
class ToolDef:
    """工具定义数据类，描述一个可注册的工具。

    Attributes:
        name: 工具名称，唯一标识
        description: 工具功能描述
        function: 异步工具函数
        parameters: 参数定义字典，key 为参数名，value 为包含 type/description/required 的字典
    """

    name: str
    description: str
    function: ToolFn
    parameters: dict[str, dict[str, Any]]


def _to_openai_function(name: str, description: str, params: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """将工具定义转换为 OpenAI function calling 格式。

    Args:
        name: 函数名称
        description: 函数描述
        params: 参数定义字典

    Returns:
        OpenAI 兼容的 function 定义字典
    """
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


class ToolRegistry:
    """工具注册表，管理工具的注册、查询和调用。

    提供装饰器注册和手动注册两种方式，支持按名称查找工具函数、
    生成 OpenAI 兼容的工具列表以及调用已注册的工具。
    """

    def __init__(self) -> None:
        """初始化空的工具注册表。"""
        self._tools: dict[str, ToolDef] = {}

    def register(self, fn: ToolFn, name: str, description: str, parameters: dict[str, dict[str, Any]]) -> None:
        """手动注册一个工具。

        Args:
            fn: 异步工具函数
            name: 工具名称，必须唯一
            description: 工具功能描述
            parameters: 参数定义字典
        """
        self._tools[name] = ToolDef(
            name=name,
            description=description,
            function=fn,
            parameters=parameters,
        )

    def tool(self, name: str, description: str, parameters: dict[str, dict[str, Any]]) -> Callable:
        """装饰器方式注册工具。

        用法: @registry.tool(name="xxx", description="xxx", parameters={...})

        Args:
            name: 工具名称
            description: 工具功能描述
            parameters: 参数定义字典

        Returns:
            装饰器函数
        """

        def decorator(fn: ToolFn) -> ToolFn:
            self.register(fn, name, description, parameters)
            return fn

        return decorator

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """获取所有已注册工具的 OpenAI function calling 格式列表。

        Returns:
            OpenAI 兼容的 function 定义列表
        """
        return [_to_openai_function(t.name, t.description, t.parameters) for t in self._tools.values()]

    def get_tool_fn(self, name: str) -> ToolFn | None:
        """根据名称获取工具函数。

        Args:
            name: 工具名称

        Returns:
            工具函数，不存在时返回 None
        """
        tool = self._tools.get(name)
        return tool.function if tool else None

    def unregister(self, name: str) -> None:
        """注销指定工具。

        Args:
            name: 工具名称
        """
        self._tools.pop(name, None)

    def list_tool_names(self) -> list[str]:
        """列出所有已注册的工具名称。

        Returns:
            工具名称列表
        """
        return list(self._tools.keys())

    async def call_tool(self, name: str, **kwargs) -> str:
        """调用指定工具。

        Args:
            name: 工具名称
            **kwargs: 传递给工具函数的参数

        Returns:
            JSON 格式的工具执行结果
        """
        if name not in self._tools:
            return error_response(f"未知工具: {name}", "UNKNOWN_TOOL")
        logger.debug("ToolRegistry - 调用工具 | tool=%s args_len=%d", name, len(kwargs))
        tool = self._tools[name]
        try:
            return await tool.function(**kwargs)
        except TypeError as e:
            return error_response(f"工具参数错误: {str(e)}", "INVALID_PARAMETERS")
        except Exception as e:
            return error_response(f"工具执行失败: {str(e)}", "EXECUTION_ERROR")


# ---------------------------------------------------------------------------
# 默认注册表实例 + 内置工具注册
# ---------------------------------------------------------------------------

_default_registry = ToolRegistry()

_default_registry.register(
    fn=run_shell,
    name="run_shell",
    description="执行终端命令",
    parameters={
        "cmd": {"type": "string", "description": "要执行的 shell 命令", "required": True},
    },
)

_default_registry.register(
    fn=read_file,
    name="read_file",
    description="读取文件内容",
    parameters={
        "path": {"type": "string", "description": "文件路径", "required": True},
    },
)

_default_registry.register(
    fn=write_file,
    name="write_file",
    description="写入文件内容",
    parameters={
        "path": {"type": "string", "description": "文件路径", "required": True},
        "content": {"type": "string", "description": "文件内容", "required": True},
    },
)

_default_registry.register(
    fn=edit_file,
    name="edit_file",
    description="编辑文件内容（精确替换旧字符串为新字符串）",
    parameters={
        "path": {"type": "string", "description": "文件路径", "required": True},
        "oldString": {"type": "string", "description": "要替换的旧字符串", "required": True},
        "newString": {"type": "string", "description": "新字符串", "required": True},
        "replaceAll": {"type": "boolean", "description": "是否替换所有匹配项（默认 false）", "required": False},
    },
)

# todo_write — 自包含工具，直接内联注册


async def _todo_write_tool(todos: str) -> str:
    """创建和更新任务列表的工具封装。"""
    try:
        items = json.loads(todos)
        if not isinstance(items, list):
            return error_response("todos 必须是 JSON 数组", "INVALID_PARAMETERS")
        return success_response({"todos": items, "count": len(items)})
    except json.JSONDecodeError as e:
        return error_response(f"todos JSON 解析失败: {e}", "INVALID_PARAMETERS")


_default_registry.register(
    fn=_todo_write_tool,
    name="todo_write",
    description="创建和更新结构化任务列表，用于跟踪多步骤工作的进度",
    parameters={
        "todos": {
            "type": "string",
            "description": "JSON 字符串，任务数组，每项含 content/status/priority 字段",
            "required": True,
        },
    },
)

# skill 工具 — 按需加载 skill 指令


async def _skill_tool(name: str) -> str:
    """加载 skill 完整指令的工具封装。"""
    from src.skills.tool import skill_tool as _skill_tool_impl

    return await _skill_tool_impl(name=name)


_default_registry.register(
    fn=_skill_tool,
    name="skill",
    description="加载指定 skill 的完整指令。当任务匹配某个 skill 的描述时使用此工具获取详细指引。",
    parameters={
        "name": {"type": "string", "description": "skill 名称", "required": True},
    },
)


__all__ = ["ToolDef", "ToolFn", "ToolRegistry", "_default_registry"]

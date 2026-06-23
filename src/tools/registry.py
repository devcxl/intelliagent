from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from src.utils.logger import logger

from .file_tools import edit_file, read_file, write_file
from .response import error_response
from .shell_tool import run_shell
from .task_tools import task_add, task_finish, task_update, task_write

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

    async def call_tool(self, tool_name: str, **kwargs) -> str:
        """调用指定工具。

        Args:
            tool_name: 工具名称
            **kwargs: 传递给工具函数的参数

        Returns:
            JSON 格式的工具执行结果
        """
        if tool_name not in self._tools:
            return error_response(f"未知工具: {tool_name}", "UNKNOWN_TOOL")
        logger.debug("ToolRegistry - 调用工具 | tool=%s args_len=%d", tool_name, len(kwargs))
        tool = self._tools[tool_name]
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

# task 工具 — 任务 CRUD，持久化到 SQLite


_default_registry.register(
    fn=task_write,
    name="task_write",
    description="批量创建任务列表，用于跟踪多步骤工作的进度。每项含 title(必填)/content/priority/parent_id",
    parameters={
        "tasks": {
            "type": "string",
            "description": "JSON 字符串，任务数组，每项含 title/content/priority/parent_id 字段",
            "required": True,
        },
    },
)

_default_registry.register(
    fn=task_add,
    name="task_add",
    description="创建单条任务",
    parameters={
        "title": {"type": "string", "description": "任务标题", "required": True},
        "content": {"type": "string", "description": "任务详细描述", "required": False},
        "priority": {"type": "string", "description": "优先级（high/medium/low），默认 medium", "required": False},
        "parent_id": {"type": "string", "description": "父任务 ID，空字符串为顶级任务", "required": False},
    },
)

_default_registry.register(
    fn=task_update,
    name="task_update",
    description="更新单条任务，只更新传入的非空字段",
    parameters={
        "id": {"type": "string", "description": "任务 ID", "required": True},
        "title": {"type": "string", "description": "新标题，空字符串不更新", "required": False},
        "content": {"type": "string", "description": "新内容，空字符串不更新", "required": False},
        "status": {
            "type": "string",
            "description": "新状态（pending/in_progress/completed/cancelled），空字符串不更新",
            "required": False,
        },
        "priority": {"type": "string", "description": "新优先级，空字符串不更新", "required": False},
    },
)

_default_registry.register(
    fn=task_finish,
    name="task_finish",
    description="标记任务为已完成",
    parameters={
        "id": {"type": "string", "description": "任务 ID", "required": True},
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

# agent-team 工具 — Agent 间通信与团队管理


def _register_agent_team_tools() -> None:
    """惰性注册 agent-team 工具，避免循环引用。

    agent_team_tools → src.core.agent_team → ReactEngine → _default_registry
    的循环依赖要求在 _default_registry 完全初始化后才能导入 agent_team_tools。
    """
    from .agent_team_tools import (
        create_agent,
        delete_agent,
        get_contact_detail,
        get_contacts,
        receive_message,
        send_message,
    )

    _default_registry.register(
        fn=send_message,
        name="send_message",
        description="向指定 Agent 发送消息。需要目标 Agent ID 和消息内容。发送方身份由系统上下文自动确定。",
        parameters={
            "to_agent_id": {"type": "string", "description": "目标 Agent ID", "required": True},
            "content": {"type": "string", "description": "消息内容", "required": True},
        },
    )

    _default_registry.register(
        fn=receive_message,
        name="receive_message",
        description="接收发送给当前 Agent 的消息（收件箱）。返回的消息会自动标记为已读。支持分页和未读过滤。",
        parameters={
            "limit": {"type": "integer", "description": "返回消息数量上限，默认 20", "required": False},
            "offset": {"type": "integer", "description": "分页偏移量，默认 0", "required": False},
            "unread_only": {"type": "boolean", "description": "仅返回未读消息，默认 false", "required": False},
        },
    )

    _default_registry.register(
        fn=get_contacts,
        name="get_contacts",
        description="获取 Agent 通讯录列表。返回所有 Agent（排除当前 Agent），可按在线状态筛选。",
        parameters={
            "status": {
                "type": "string",
                "description": "按状态筛选：online / offline / busy。不传则返回全部。",
                "required": False,
            },
        },
    )

    _default_registry.register(
        fn=get_contact_detail,
        name="get_contact_detail",
        description="获取指定 Agent 的详细信息，包括名称、描述、状态等。",
        parameters={
            "agent_id": {"type": "string", "description": "Agent ID", "required": True},
        },
    )

    _default_registry.register(
        fn=create_agent,
        name="create_agent",
        description="创建一个新的 Agent。Agent ID 由系统自动生成，只需提供名称、描述和系统 Prompt。",
        parameters={
            "name": {"type": "string", "description": "Agent 名称（必须唯一）", "required": True},
            "desc": {"type": "string", "description": "Agent 描述", "required": False},
            "prompt": {"type": "string", "description": "Agent 系统 Prompt", "required": False},
        },
    )

    _default_registry.register(
        fn=delete_agent,
        name="delete_agent",
        description="删除指定 Agent。执行软删除（状态标记为 deleted），历史消息保留。",
        parameters={
            "agent_id": {"type": "string", "description": "要删除的 Agent ID", "required": True},
        },
    )


_register_agent_team_tools()

__all__ = ["ToolDef", "ToolFn", "ToolRegistry", "_default_registry"]

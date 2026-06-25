from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Coroutine

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.skills.registry import SkillRegistry
from src.tools.agent_team_tools import AgentTeamTools
from src.tools.file_tools import edit_file, read_file, write_file
from src.tools.response import error_response
from src.tools.shell_tool import run_shell
from src.tools.task_tools import TaskTools
from src.utils.logger import logger

if TYPE_CHECKING:
    from src.skills.tool import SkillTool

ToolFn = Callable[..., Coroutine[Any, Any, str]]
SessionFactoryProvider = Callable[[], async_sessionmaker[AsyncSession]]
ConversationIdProvider = Callable[[], str | None]


@dataclass
class ToolDef:
    """工具定义数据类，描述一个可注册的工具。"""

    name: str
    description: str
    function: ToolFn
    parameters: dict[str, dict[str, Any]]


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


class ToolRegistry:
    """工具注册表，管理工具的注册、查询和调用。"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, fn: ToolFn, name: str, description: str, parameters: dict[str, dict[str, Any]]) -> None:
        self._tools[name] = ToolDef(
            name=name,
            description=description,
            function=fn,
            parameters=parameters,
        )

    def tool(self, name: str, description: str, parameters: dict[str, dict[str, Any]]) -> Callable:
        def decorator(fn: ToolFn) -> ToolFn:
            self.register(fn, name, description, parameters)
            return fn

        return decorator

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [_to_openai_function(t.name, t.description, t.parameters) for t in self._tools.values()]

    def get_tool_fn(self, name: str) -> ToolFn | None:
        tool = self._tools.get(name)
        return tool.function if tool else None

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str:
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


class ToolRegistryFactory:
    """创建 Runtime 级 ToolRegistry，避免模块级全局可变注册表。"""

    def __init__(
        self,
        session_factory_provider: SessionFactoryProvider,
        conversation_id_provider: ConversationIdProvider,
        agent_id: str,
        skill_registry: SkillRegistry | None = None,
    ) -> None:
        self._session_factory_provider = session_factory_provider
        self._conversation_id_provider = conversation_id_provider
        self._agent_id = agent_id
        self._skill_registry = skill_registry

    def create_default(self) -> ToolRegistry:
        registry = ToolRegistry()
        register_builtin_tools(registry)
        register_task_tools(
            registry,
            TaskTools(
                session_factory_provider=self._session_factory_provider,
                conversation_id_provider=self._conversation_id_provider,
            ),
        )
        register_agent_team_tools(
            registry,
            AgentTeamTools(
                session_factory_provider=self._session_factory_provider,
                agent_id=self._agent_id,
            ),
        )
        if self._skill_registry is not None:
            from src.skills.tool import SkillTool

            register_skill_tool(registry, SkillTool(self._skill_registry))
        return registry


def register_builtin_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(
        fn=run_shell,
        name="run_shell",
        description="执行终端命令",
        parameters={"cmd": {"type": "string", "description": "要执行的 shell 命令", "required": True}},
    )
    registry.register(
        fn=read_file,
        name="read_file",
        description="读取文件内容",
        parameters={"path": {"type": "string", "description": "文件路径", "required": True}},
    )
    registry.register(
        fn=write_file,
        name="write_file",
        description="写入文件内容",
        parameters={
            "path": {"type": "string", "description": "文件路径", "required": True},
            "content": {"type": "string", "description": "文件内容", "required": True},
        },
    )
    registry.register(
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
    return registry


def register_task_tools(registry: ToolRegistry, tools: TaskTools) -> ToolRegistry:
    registry.register(
        fn=tools.task_write,
        name="task_write",
        description="批量创建任务列表，用于跟踪多步骤工作的进度。每项含 title(必填)/content/priority/parent_id",
        parameters={
            "tasks": {
                "type": "string",
                "description": "JSON 字符串，任务数组，每项含 title/content/priority/parent_id 字段",
                "required": True,
            }
        },
    )
    registry.register(
        fn=tools.task_add,
        name="task_add",
        description="创建单条任务",
        parameters={
            "title": {"type": "string", "description": "任务标题", "required": True},
            "content": {"type": "string", "description": "任务详细描述", "required": False},
            "priority": {"type": "string", "description": "优先级（high/medium/low），默认 medium", "required": False},
            "parent_id": {"type": "string", "description": "父任务 ID，空字符串为顶级任务", "required": False},
        },
    )
    registry.register(
        fn=tools.task_update,
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
    registry.register(
        fn=tools.task_finish,
        name="task_finish",
        description="标记任务为已完成",
        parameters={"id": {"type": "string", "description": "任务 ID", "required": True}},
    )
    return registry


def register_skill_tool(registry: ToolRegistry, tool: SkillTool) -> ToolRegistry:
    registry.register(
        fn=tool.load,
        name="skill",
        description="加载指定 skill 的完整指令。当任务匹配某个 skill 的描述时使用此工具获取详细指引。",
        parameters={"name": {"type": "string", "description": "skill 名称", "required": True}},
    )
    return registry


def register_agent_team_tools(registry: ToolRegistry, tools: AgentTeamTools) -> ToolRegistry:
    registry.register(
        fn=tools.send_message,
        name="send_message",
        description="向指定 Agent 发送消息。需要目标 Agent ID 和消息内容。发送方身份由系统上下文自动确定。",
        parameters={
            "to_agent_id": {"type": "string", "description": "目标 Agent ID", "required": True},
            "content": {"type": "string", "description": "消息内容", "required": True},
        },
    )
    registry.register(
        fn=tools.receive_message,
        name="receive_message",
        description="接收发送给当前 Agent 的消息（收件箱）。返回的消息会自动标记为已读。支持分页和未读过滤。",
        parameters={
            "limit": {"type": "integer", "description": "返回消息数量上限，默认 20", "required": False},
            "offset": {"type": "integer", "description": "分页偏移量，默认 0", "required": False},
            "unread_only": {"type": "boolean", "description": "仅返回未读消息，默认 false", "required": False},
        },
    )
    registry.register(
        fn=tools.get_contacts,
        name="get_contacts",
        description="获取 Agent 通讯录列表。返回所有 Agent（排除当前 Agent），可按在线状态筛选。",
        parameters={
            "status": {
                "type": "string",
                "description": "按状态筛选：online / offline / busy。不传则返回全部。",
                "required": False,
            }
        },
    )
    registry.register(
        fn=tools.get_contact_detail,
        name="get_contact_detail",
        description="获取指定 Agent 的详细信息，包括名称、描述、状态等。",
        parameters={"agent_id": {"type": "string", "description": "Agent ID", "required": True}},
    )
    registry.register(
        fn=tools.create_agent,
        name="create_agent",
        description="创建一个新的 Agent。Agent ID 由系统自动生成，只需提供名称、描述和系统 Prompt。",
        parameters={
            "name": {"type": "string", "description": "Agent 名称（必须唯一）", "required": True},
            "desc": {"type": "string", "description": "Agent 描述", "required": False},
            "prompt": {"type": "string", "description": "Agent 系统 Prompt", "required": False},
            "allowed_tools": {"type": "string", "description": "允许使用的工具列表", "required": False},
            "model": {"type": "string", "description": "Agent 使用的模型", "required": False},
            "workspace": {"type": "string", "description": "Agent 工作区路径", "required": False},
        },
    )
    registry.register(
        fn=tools.delete_agent,
        name="delete_agent",
        description="删除指定 Agent。执行软删除（状态标记为 deleted），历史消息保留。",
        parameters={"agent_id": {"type": "string", "description": "要删除的 Agent ID", "required": True}},
    )
    return registry


__all__ = [
    "ToolDef",
    "ToolFn",
    "ToolRegistry",
    "ToolRegistryFactory",
    "register_agent_team_tools",
    "register_builtin_tools",
    "register_skill_tool",
    "register_task_tools",
]

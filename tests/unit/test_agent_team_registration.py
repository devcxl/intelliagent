"""Agent-team 工具注册单元测试。"""

from src.tools.agent_team_tools import AgentTeamTools
from src.tools.registry import ToolRegistry, ToolRegistryFactory, register_agent_team_tools


def _unused_factory():
    raise AssertionError("注册测试不应真正创建数据库 session")


def _register_agent_team_registry() -> ToolRegistry:
    return register_agent_team_tools(ToolRegistry(), AgentTeamTools(_unused_factory, "agent-001"))


def test_agent_team_tools_registered_in_custom_registry():
    registry = _register_agent_team_registry()
    names = registry.list_tool_names()
    expected = {"send_message", "receive_message", "get_contacts", "get_contact_detail", "create_agent", "delete_agent"}
    for name in expected:
        assert name in names, f"{name} 未注册"


def test_send_message_has_correct_parameters():
    tool_def = _register_agent_team_registry()._tools.get("send_message")
    assert tool_def is not None
    assert tool_def.parameters["to_agent_id"]["required"] is True
    assert tool_def.parameters["content"]["required"] is True


def test_receive_message_has_correct_parameters():
    tool_def = _register_agent_team_registry()._tools.get("receive_message")
    assert tool_def is not None
    assert tool_def.parameters["limit"]["required"] is False
    assert tool_def.parameters["offset"]["required"] is False
    assert tool_def.parameters["unread_only"]["type"] == "boolean"


def test_create_agent_has_correct_parameters():
    tool_def = _register_agent_team_registry()._tools.get("create_agent")
    assert tool_def is not None
    assert tool_def.parameters["name"]["required"] is True
    assert tool_def.parameters["allowed_tools"]["required"] is False


def test_factory_registers_agent_team_tools():
    registry = ToolRegistryFactory(
        session_factory_provider=_unused_factory,
        conversation_id_provider=lambda: "conv-1",
        agent_id="agent-001",
    ).create_default()

    names = set(registry.list_tool_names())
    expected = {"send_message", "receive_message", "get_contacts", "get_contact_detail", "create_agent", "delete_agent"}
    assert expected <= names

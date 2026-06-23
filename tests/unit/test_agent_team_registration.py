"""Agent-team 工具注册单元测试。"""


def test_agent_team_tools_registered_in_default_registry():
    """6 个 agent-team tool 已注册到 _default_registry。"""
    from src.tools.registry import _default_registry

    names = _default_registry.list_tool_names()
    expected = {"send_message", "receive_message", "get_contacts",
                "get_contact_detail", "create_agent", "delete_agent"}
    for name in expected:
        assert name in names, f"{name} 未在 _default_registry 中"


def test_send_message_has_correct_parameters():
    """send_message 参数定义正确。"""
    from src.tools.registry import _default_registry

    tool_def = _default_registry._tools.get("send_message")
    assert tool_def is not None
    assert tool_def.parameters["to_agent_id"]["required"] is True
    assert tool_def.parameters["content"]["required"] is True
    assert tool_def.parameters["to_agent_id"]["type"] == "string"
    assert tool_def.parameters["content"]["type"] == "string"


def test_receive_message_has_correct_parameters():
    """receive_message 参数定义正确。"""
    from src.tools.registry import _default_registry

    tool_def = _default_registry._tools.get("receive_message")
    assert tool_def is not None
    assert tool_def.parameters["limit"]["required"] is False
    assert tool_def.parameters["offset"]["required"] is False
    assert tool_def.parameters["unread_only"]["required"] is False
    assert tool_def.parameters["limit"]["type"] == "integer"
    assert tool_def.parameters["unread_only"]["type"] == "boolean"


def test_create_agent_has_correct_parameters():
    """create_agent 参数定义正确。"""
    from src.tools.registry import _default_registry

    tool_def = _default_registry._tools.get("create_agent")
    assert tool_def is not None
    assert tool_def.parameters["name"]["required"] is True
    assert tool_def.parameters["desc"]["required"] is False
    assert tool_def.parameters["prompt"]["required"] is False


def test_get_openai_tools_contains_agent_team_tools():
    """get_openai_tools() 返回的列表包含 6 个 agent-team tool。"""
    from src.tools.registry import _default_registry

    tools = _default_registry.get_openai_tools()
    agent_team_names = {t["function"]["name"] for t in tools} & {
        "send_message", "receive_message", "get_contacts",
        "get_contact_detail", "create_agent", "delete_agent",
    }
    assert len(agent_team_names) == 6

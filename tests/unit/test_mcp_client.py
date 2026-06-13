from __future__ import annotations

from src.mcp.config import MCPConfig, MCPServerConfig
from src.mcp.manager import _mcp_tool_name, _tool_params_to_openai


def test_mcp_config_from_dict():
    data = {
        "servers": [
            {"name": "fs", "command": "npx", "args": ["-y", "server-fs"]},
        ],
    }
    config = MCPConfig.from_dict(data)
    assert len(config.servers) == 1
    assert config.servers[0].name == "fs"
    assert config.servers[0].command == "npx"
    assert config.servers[0].args == ["-y", "server-fs"]


def test_mcp_config_empty():
    config = MCPConfig()
    assert config.servers == []


def test_mcp_config_with_env():
    config = MCPConfig.from_dict({
        "servers": [
            {
                "name": "github",
                "command": "npx",
                "args": ["-y", "server-github"],
                "env": {"GITHUB_TOKEN": "xxx"},
            },
        ],
    })
    assert config.servers[0].env == {"GITHUB_TOKEN": "xxx"}


def test_mcp_tool_name_prefix():
    result = _mcp_tool_name("filesystem", "read_file")
    assert result == "mcp_filesystem_read_file"


def test_tool_params_to_openai_converts_input_schema():
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "recursive": {"type": "boolean", "description": "是否递归"},
        },
        "required": ["path"],
    }
    params = _tool_params_to_openai(schema)
    assert "path" in params
    assert params["path"]["type"] == "string"
    assert params["path"]["required"] is True
    assert "recursive" in params
    assert params["recursive"]["type"] == "boolean"
    assert params["recursive"]["required"] is False


def test_tool_params_to_openai_empty():
    assert _tool_params_to_openai({}) == {}
    assert _tool_params_to_openai({"type": "object"}) == {}

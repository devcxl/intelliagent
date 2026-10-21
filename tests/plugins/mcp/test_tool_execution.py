"""MCP 工具执行测试：tools/call 结果转统一信封，isError → status:"error"，经流水线回填 Observation。"""

from __future__ import annotations

import json
from typing import Any

from src.core.plugin_host import CapabilityKind, PluginHost
from src.core.tool_pipeline import ToolPipeline, ToolRequest
from src.plugins.mcp import McpPlugin, McpTool
from src.plugins.mcp.connection import McpCallResult
from tests.plugins.mcp.fakes import FakeConnection, FakeConnector, demo_config, tool_definition

ECHO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"query": {"type": "string"}, "mode": {"type": "string"}},
}


def envelope(result: str) -> dict[str, Any]:
    data = json.loads(result)
    assert isinstance(data, dict)
    return data


async def pipeline_with(
    connection: FakeConnection,
) -> tuple[ToolPipeline, FakeConnection]:
    plugin = McpPlugin(demo_config(), connector=FakeConnector({"demo": connection}))
    await plugin.connect()
    host = PluginHost()
    host.load(plugin)
    return ToolPipeline.from_host(host), connection


class TestMcpToolExecution:
    async def test_success_result_is_an_ok_envelope_with_server_content(self) -> None:
        connection = FakeConnection(
            [tool_definition("echo", schema=ECHO_SCHEMA)],
            results={"echo": McpCallResult(text="pong", is_error=False)},
        )
        pipeline, _connection = await pipeline_with(connection)

        observation = await pipeline.run(ToolRequest(tool_call_id="t1", name="mcp_demo_echo", arguments={"query": "x"}))

        data = envelope(observation.content)
        assert data["status"] == "ok"
        assert data["content"] == "pong"

    async def test_result_content_is_filled_back_into_the_observation(self) -> None:
        connection = FakeConnection(
            [tool_definition("echo", schema=ECHO_SCHEMA)],
            results={"echo": McpCallResult(text="server says hi", is_error=False)},
        )
        pipeline, _connection = await pipeline_with(connection)

        observation = await pipeline.run(ToolRequest(tool_call_id="t2", name="mcp_demo_echo", arguments={}))

        assert observation.status == "success"
        assert "server says hi" in observation.content
        assert observation.error is None

    async def test_is_error_result_becomes_an_error_envelope(self) -> None:
        connection = FakeConnection(
            [tool_definition("echo", schema=ECHO_SCHEMA)],
            results={"echo": McpCallResult(text="bad input", is_error=True)},
        )
        pipeline, _connection = await pipeline_with(connection)

        observation = await pipeline.run(ToolRequest(tool_call_id="t3", name="mcp_demo_echo", arguments={}))

        data = envelope(observation.content)
        assert data["status"] == "error"
        assert "bad input" in data["error"]
        assert observation.status == "error"
        assert observation.error is not None
        assert "bad input" in observation.error

    async def test_is_error_envelope_identifies_server_and_tool(self) -> None:
        connection = FakeConnection(
            [tool_definition("echo", schema=ECHO_SCHEMA)],
            results={"echo": McpCallResult(text="boom", is_error=True)},
        )
        pipeline, _connection = await pipeline_with(connection)

        observation = await pipeline.run(ToolRequest(tool_call_id="t4", name="mcp_demo_echo", arguments={}))
        data = envelope(observation.content)

        assert data["server"] == "demo"
        assert data["tool"] == "echo"

    async def test_empty_error_text_still_yields_a_diagnosable_message(self) -> None:
        connection = FakeConnection(
            [tool_definition("echo", schema=ECHO_SCHEMA)],
            results={"echo": McpCallResult(text="", is_error=True)},
        )
        pipeline, _connection = await pipeline_with(connection)

        observation = await pipeline.run(ToolRequest(tool_call_id="t5", name="mcp_demo_echo", arguments={}))
        data = envelope(observation.content)

        assert data["status"] == "error"
        assert data["error"]
        assert "demo" in data["error"] and "echo" in data["error"]

    async def test_transport_exception_becomes_an_error_envelope(self) -> None:
        connection = FakeConnection(
            [tool_definition("echo", schema=ECHO_SCHEMA)], call_error=RuntimeError("connection reset")
        )
        pipeline, _connection = await pipeline_with(connection)

        observation = await pipeline.run(ToolRequest(tool_call_id="t6", name="mcp_demo_echo", arguments={}))
        data = envelope(observation.content)

        assert data["status"] == "error"
        assert "connection reset" in data["error"]
        assert data["server"] == "demo"
        assert data["tool"] == "echo"
        assert observation.status == "error"

    async def test_arguments_reach_the_server_untouched(self) -> None:
        connection = FakeConnection([tool_definition("echo", schema=ECHO_SCHEMA)])
        pipeline, connection = await pipeline_with(connection)

        await pipeline.run(
            ToolRequest(tool_call_id="t7", name="mcp_demo_echo", arguments={"query": "hi", "mode": "fast"})
        )

        assert connection.calls == [("echo", {"query": "hi", "mode": "fast"})]


class TestMcpToolProvider:
    async def test_registered_capability_is_an_mcp_tool(self) -> None:
        connection = FakeConnection([tool_definition("echo", schema=ECHO_SCHEMA)])
        plugin = McpPlugin(demo_config(), connector=FakeConnector({"demo": connection}))
        await plugin.connect()
        host = PluginHost()
        host.load(plugin)

        tool = host.get_capability(CapabilityKind.TOOL, "mcp_demo_echo")

        assert isinstance(tool, McpTool)
        assert tool.name == "mcp_demo_echo"

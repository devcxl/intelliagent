"""inputSchema 完整透传测试（US16）：嵌套 object/enum/items 不降级，模型可正确构造复杂参数。

旧缺陷（docs/2026-10-21-project-analysis-and-roadmap.md）：schema 转换把 MCP inputSchema
扁平化为 {type, description, required}，嵌套 object/enum/items 全丢，模型无法构造复杂参数。
"""

from __future__ import annotations

from typing import Any

from src.plugins.mcp import McpPlugin, McpTool

from src.core.plugin_host import CapabilityKind, PluginHost
from src.core.tool_pipeline import Observation, ToolPipeline, ToolRequest
from tests.plugins.mcp.fakes import NESTED_INPUT_SCHEMA, FakeConnection, FakeConnector, demo_config, tool_definition

NESTED_ARGUMENTS: dict[str, Any] = {
    "query": "hello",
    "mode": "thorough",
    "filters": {
        "tags": ["a", "b"],
        "limits": {"max": 5, "unit": "mb"},
    },
    "targets": [{"path": "src", "depth": 2}, {"path": "docs"}],
}


async def loaded_tool() -> tuple[McpTool, FakeConnection]:
    """经 PluginHost 加载 demo 服务器的 search 工具，返回能力提供者与 fake 连接。"""
    connection = FakeConnection([tool_definition("search")])
    plugin = McpPlugin(demo_config(), connector=FakeConnector({"demo": connection}))
    await plugin.connect()
    host = PluginHost()
    host.load(plugin)
    tool = host.get_capability(CapabilityKind.TOOL, "mcp_demo_search")
    assert isinstance(tool, McpTool)
    return tool, connection


class TestInputSchemaPassthrough:
    async def test_parameters_are_the_exact_mcp_input_schema(self) -> None:
        tool, _connection = await loaded_tool()

        assert tool.parameters == NESTED_INPUT_SCHEMA

    async def test_nested_enums_and_items_survive_registration(self) -> None:
        tool, _connection = await loaded_tool()

        properties = tool.parameters["properties"]
        assert properties["mode"]["enum"] == ["fast", "thorough"]
        assert properties["filters"]["properties"]["tags"]["items"] == {"type": "string"}
        assert properties["targets"]["items"]["required"] == ["path"]
        assert tool.parameters["required"] == ["query"]

    async def test_pipeline_accepts_nested_arguments(self) -> None:
        tool, connection = await loaded_tool()
        pipeline = ToolPipeline({"mcp_demo_search": tool})

        observation = await pipeline.run(
            ToolRequest(tool_call_id="t1", name="mcp_demo_search", arguments=NESTED_ARGUMENTS)
        )

        assert observation.status == "success"
        assert connection.calls == [("search", NESTED_ARGUMENTS)]

    async def test_pipeline_enforces_nested_schema_instead_of_degrading_it(self) -> None:
        tool, _connection = await loaded_tool()
        pipeline = ToolPipeline({"mcp_demo_search": tool})
        broken = dict(NESTED_ARGUMENTS, mode="ultra")

        observation = await pipeline.run(ToolRequest(tool_call_id="t2", name="mcp_demo_search", arguments=broken))

        assert observation.status == "error"
        assert observation.error is not None
        assert "mode" in observation.error

    async def test_pipeline_rejects_missing_nested_required_fields(self) -> None:
        tool, connection = await loaded_tool()
        pipeline = ToolPipeline({"mcp_demo_search": tool})
        broken = dict(NESTED_ARGUMENTS, filters={"limits": {"max": 1}})

        observation = await pipeline.run(ToolRequest(tool_call_id="t3", name="mcp_demo_search", arguments=broken))

        assert observation.status == "error"
        assert connection.calls == []


class TestSchemaPassthroughIntegration:
    async def test_roundtrip_preserves_nested_arguments_at_the_server(self) -> None:
        """完整链路：PluginHost 注册 → 流水线校验 → server 收到的参数与模型构造的完全一致。"""
        connection = FakeConnection([tool_definition("search", description="搜索")])
        plugin = McpPlugin(demo_config(), connector=FakeConnector({"demo": connection}))
        await plugin.connect()
        host = PluginHost()
        host.load(plugin)
        pipeline = ToolPipeline.from_host(host)

        observation = await pipeline.run(
            ToolRequest(tool_call_id="t4", name="mcp_demo_search", arguments=NESTED_ARGUMENTS)
        )

        assert observation.status == "success"
        assert connection.calls == [("search", NESTED_ARGUMENTS)]
        assert isinstance(observation, Observation)

"""插件契约集成测试：mcp 内置插件经 PluginHost 注册 TOOL 能力（与外部插件同一契约，ADR 0007）。"""

from __future__ import annotations

import pytest
from src.plugins.mcp import McpPlugin, McpPluginConfig, McpTool
from src.plugins.mcp.errors import McpPluginError

from src.core.plugin_host import CapabilityKind, PluginHost
from src.core.tool_pipeline import ToolPipeline, ToolRequest
from tests.plugins.mcp.fakes import FakeConnection, FakeConnector, demo_config, tool_definition


async def connected_plugin(
    tools_per_server: dict[str, list[str]],
) -> tuple[McpPlugin, dict[str, FakeConnection]]:
    """按 {server: [tool, ...]} 构造 fake 连接器并完成 connect，返回插件与各服务器连接。"""
    connections = {
        server: FakeConnection([tool_definition(name) for name in names]) for server, names in tools_per_server.items()
    }
    plugin = McpPlugin(demo_config(*tools_per_server.keys()), connector=FakeConnector(connections))
    await plugin.connect()
    return plugin, connections


class TestMcpPluginContract:
    async def test_manifest_declares_the_discovered_tool_capabilities(self) -> None:
        plugin, _connections = await connected_plugin({"demo": ["alpha", "beta"]})

        declared = {(item.kind, item.name) for item in plugin.manifest.capabilities}

        assert declared == {
            (CapabilityKind.TOOL, "mcp_demo_alpha"),
            (CapabilityKind.TOOL, "mcp_demo_beta"),
        }
        assert plugin.manifest.name == "mcp"
        assert plugin.manifest.api_version == 1

    async def test_manifest_carries_the_plugin_config_schema(self) -> None:
        plugin, _connections = await connected_plugin({"demo": ["alpha"]})

        assert plugin.manifest.config_schema is McpPluginConfig

    async def test_host_registers_each_mcp_tool_as_a_tool_capability(self) -> None:
        plugin, _connections = await connected_plugin({"demo": ["alpha", "beta"]})
        host = PluginHost()
        host.load(plugin)

        tools = host.capabilities(CapabilityKind.TOOL)

        assert set(tools) == {"mcp_demo_alpha", "mcp_demo_beta"}
        assert all(isinstance(tool, McpTool) for tool in tools.values())

    async def test_registered_tools_execute_through_the_pipeline(self) -> None:
        connection = FakeConnection([tool_definition("alpha")])
        plugin = McpPlugin(demo_config("demo"), connector=FakeConnector({"demo": connection}))
        await plugin.connect()
        host = PluginHost()
        host.load(plugin)
        pipeline = ToolPipeline.from_host(host)

        observation = await pipeline.run(
            ToolRequest(tool_call_id="t1", name="mcp_demo_alpha", arguments={"query": "hello"})
        )

        assert observation.status == "success"
        assert connection.calls == [("alpha", {"query": "hello"})]

    async def test_loading_before_connect_fails_with_a_diagnosable_error(self) -> None:
        plugin = McpPlugin(demo_config("demo"), connector=FakeConnector({}))

        with pytest.raises(McpPluginError) as excinfo:
            PluginHost().load(plugin)

        assert "connect" in str(excinfo.value)

    async def test_discovering_no_tools_is_an_explicit_error(self) -> None:
        plugin = McpPlugin(demo_config("demo"), connector=FakeConnector({"demo": FakeConnection([])}))

        with pytest.raises(McpPluginError) as excinfo:
            await plugin.connect()

        message = str(excinfo.value)
        assert "demo" in message
        assert "tool" in message


class TestMcpPluginLifecycle:
    async def test_close_closes_every_server_connection(self) -> None:
        plugin, connections = await connected_plugin({"alpha": ["one"], "beta": ["two"]})

        await plugin.close()

        assert all(connection.closed for connection in connections.values())

    async def test_close_is_idempotent(self) -> None:
        plugin, _connections = await connected_plugin({"demo": ["alpha"]})

        await plugin.close()
        await plugin.close()

    async def test_connect_twice_is_rejected(self) -> None:
        plugin, _connections = await connected_plugin({"demo": ["alpha"]})

        with pytest.raises(McpPluginError):
            await plugin.connect()

        await plugin.close()

    async def test_reconnect_after_close_is_possible(self) -> None:
        connection = FakeConnection([tool_definition("alpha")])
        plugin = McpPlugin(demo_config("demo"), connector=FakeConnector({"demo": connection}))
        await plugin.connect()
        await plugin.close()

        plugin = McpPlugin(demo_config("demo"), connector=FakeConnector({"demo": connection}))
        await plugin.connect()
        host = PluginHost()
        host.load(plugin)

        assert isinstance(host.get_capability(CapabilityKind.TOOL, "mcp_demo_alpha"), McpTool)


class TestMcpCapabilityNaming:
    async def test_capability_names_follow_mcp_server_tool_convention(self) -> None:
        plugin, _connections = await connected_plugin({"git-server": ["list_repos"]})
        host = PluginHost()
        host.load(plugin)

        assert set(host.capabilities(CapabilityKind.TOOL)) == {"mcp_git-server_list_repos"}

    async def test_tool_names_with_uppercase_are_normalized(self) -> None:
        plugin, _connections = await connected_plugin({"demo": ["WebSearch"]})
        host = PluginHost()
        host.load(plugin)

        assert set(host.capabilities(CapabilityKind.TOOL)) == {"mcp_demo_websearch"}

"""工具名冲突显式报错测试：能力名 mcp_{server}_{tool} 冲突绝不静默覆盖（旧缺陷）。"""

from __future__ import annotations

import pytest
from src.plugins.mcp import McpPlugin
from src.plugins.mcp.errors import McpToolConflictError

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, PluginHost
from src.core.plugin_host.errors import CapabilityConflictError
from tests.core.plugin_host.fakes import FakePlugin, build_manifest
from tests.plugins.mcp.fakes import FakeConnection, FakeConnector, demo_config, tool_definition


class TestToolNameConflicts:
    async def test_ambiguous_server_tool_split_is_rejected_explicitly(self) -> None:
        """server 'a' 的工具 'b_c' 与 server 'a_b' 的工具 'c' 都会生成能力名 mcp_a_b_c。"""
        first = FakeConnection([tool_definition("b_c")])
        second = FakeConnection([tool_definition("c")])
        connector = FakeConnector({"a": first, "a_b": second})
        plugin = _plugin(connector, "a", "a_b")

        with pytest.raises(McpToolConflictError) as excinfo:
            await plugin.connect()

        message = str(excinfo.value)
        assert "mcp_a_b_c" in message
        assert "tool 'b_c'" in message
        assert "tool 'c'" in message

    async def test_normalized_name_collision_is_rejected_explicitly(self) -> None:
        """非法规格字符与大小写规范化后同名的工具必须显式报错，指出两个来源。"""
        connection = FakeConnection([tool_definition("WebSearch"), tool_definition("websearch")])
        connector = FakeConnector({"demo": connection})
        plugin = _plugin(connector, "demo")

        with pytest.raises(McpToolConflictError) as excinfo:
            await plugin.connect()

        message = str(excinfo.value)
        assert "mcp_demo_websearch" in message
        assert "tool 'WebSearch'" in message
        assert "tool 'websearch'" in message

    async def test_conflict_closes_already_opened_connections(self) -> None:
        first = FakeConnection([tool_definition("b_c")])
        second = FakeConnection([tool_definition("c")])
        connector = FakeConnector({"a": first, "a_b": second})
        plugin = _plugin(connector, "a", "a_b")

        with pytest.raises(McpToolConflictError):
            await plugin.connect()

        assert first.closed is True and second.closed is True

    async def test_conflict_with_an_already_registered_capability_is_rejected(self) -> None:
        provider = object()
        manifest = build_manifest(
            "other-plugin",
            capabilities=(CapabilityDeclaration(kind=CapabilityKind.TOOL, name="mcp_demo_echo"),),
        )
        host = PluginHost()
        host.load(FakePlugin(manifest, providers={(CapabilityKind.TOOL, "mcp_demo_echo"): provider}))
        connection = FakeConnection([tool_definition("echo")])
        plugin = _plugin(FakeConnector({"demo": connection}), "demo")
        await plugin.connect()

        with pytest.raises(CapabilityConflictError):
            host.load(plugin)

        assert host.get_capability(CapabilityKind.TOOL, "mcp_demo_echo") is provider


def _plugin(connector: FakeConnector, *server_names: str) -> McpPlugin:
    return McpPlugin(demo_config(*server_names), connector=connector)

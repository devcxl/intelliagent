"""连接失败可诊断测试：错误含 server 标识与原因，连接超时显式（不无限等），失败不留半开连接。"""

from __future__ import annotations

import pytest
from src.plugins.mcp import McpPlugin, McpPluginConfig
from src.plugins.mcp.errors import McpConnectionError, McpPluginError

from src.core.plugin_host import PluginHost
from tests.plugins.mcp.fakes import FakeConnection, FakeConnector, demo_config, tool_definition


class TestConnectionFailureDiagnostics:
    async def test_connect_error_names_the_server_and_the_reason(self) -> None:
        connector = FakeConnector(connect_errors={"demo": RuntimeError("spawn failed: permission denied")})
        plugin = McpPlugin(demo_config("demo"), connector=connector)

        with pytest.raises(McpConnectionError) as excinfo:
            await plugin.connect()

        assert excinfo.value.server == "demo"
        assert "spawn failed: permission denied" in str(excinfo.value)
        assert "demo" in str(excinfo.value)

    async def test_error_exposes_machine_readable_server_and_reason(self) -> None:
        connector = FakeConnector(connect_errors={"demo": RuntimeError("refused")})
        plugin = McpPlugin(demo_config("demo"), connector=connector)

        with pytest.raises(McpConnectionError) as excinfo:
            await plugin.connect()

        assert excinfo.value.server == "demo"
        assert "refused" in excinfo.value.reason

    async def test_failure_on_one_server_names_that_server(self) -> None:
        good = FakeConnection([tool_definition("search")])
        connector = FakeConnector({"alpha": good}, connect_errors={"beta": RuntimeError("dns lookup failed")})
        plugin = McpPlugin(demo_config("alpha", "beta"), connector=connector)

        with pytest.raises(McpConnectionError) as excinfo:
            await plugin.connect()

        assert excinfo.value.server == "beta"
        assert "dns lookup failed" in str(excinfo.value)

    async def test_failure_closes_connections_already_opened(self) -> None:
        good = FakeConnection([tool_definition("search")])
        connector = FakeConnector({"alpha": good}, connect_errors={"beta": RuntimeError("boom")})
        plugin = McpPlugin(demo_config("alpha", "beta"), connector=connector)

        with pytest.raises(McpConnectionError):
            await plugin.connect()

        assert good.closed is True

    async def test_plugin_is_not_loadable_after_a_failed_connect(self) -> None:
        connector = FakeConnector(connect_errors={"demo": RuntimeError("boom")})
        plugin = McpPlugin(demo_config("demo"), connector=connector)
        with pytest.raises(McpConnectionError):
            await plugin.connect()

        with pytest.raises(McpPluginError) as excinfo:
            PluginHost().load(plugin)

        assert "connect" in str(excinfo.value)


class TestConnectionTimeout:
    async def test_connect_timeout_is_explicit_and_names_the_server(self) -> None:
        connector = FakeConnector(connect_delays={"slow": 30.0})
        config = demo_config("slow").servers[0].model_copy(update={"connect_timeout": 0.05})
        plugin = McpPlugin(McpPluginConfig(servers=[config]), connector=connector)

        with pytest.raises(McpConnectionError) as excinfo:
            await plugin.connect()

        assert excinfo.value.server == "slow"
        assert "timed out" in str(excinfo.value)
        assert "0.05" in str(excinfo.value)

    async def test_timeout_also_covers_tool_discovery(self) -> None:
        hanging = FakeConnection([tool_definition("search")], list_tools_delay=30.0)
        connector = FakeConnector({"slow": hanging})
        config = demo_config("slow").servers[0].model_copy(update={"connect_timeout": 0.05})
        plugin = McpPlugin(McpPluginConfig(servers=[config]), connector=connector)

        with pytest.raises(McpConnectionError) as excinfo:
            await plugin.connect()

        assert excinfo.value.server == "slow"
        assert "timed out" in str(excinfo.value)

    async def test_timed_out_connection_is_closed(self) -> None:
        hanging = FakeConnection([tool_definition("search")], list_tools_delay=30.0)
        connector = FakeConnector({"slow": hanging})
        config = demo_config("slow").servers[0].model_copy(update={"connect_timeout": 0.05})
        plugin = McpPlugin(McpPluginConfig(servers=[config]), connector=connector)

        with pytest.raises(McpConnectionError):
            await plugin.connect()

        assert hanging.closed is True

"""MCP 运行时接线：opt-in 连接、工具注册与关闭；失败不静默降级。"""

from __future__ import annotations

import pytest

from src.config.yaml_config import IntelliAgentConfig, PluginConfig
from src.core.plugin_host import CapabilityKind, PluginConfigError, PluginHost, PluginLoadError
from src.runtime.plugin_assembly import connect_mcp_plugins
from tests.plugins.mcp.fakes import FakeConnection, FakeConnector, demo_server, tool_definition


def mcp_config(*, enabled: bool = True, servers: list[dict[str, object]] | None = None) -> IntelliAgentConfig:
    config: dict[str, object] = {
        "servers": servers if servers is not None else [demo_server().model_dump(exclude_none=True)]
    }
    return IntelliAgentConfig(plugins={"mcp": PluginConfig(enabled=enabled, config=config)})


async def test_connect_registers_tools_and_close_releases_connections() -> None:
    connection = FakeConnection([tool_definition("echo")])
    connector = FakeConnector({"demo": connection})
    host = PluginHost()

    plugins = await connect_mcp_plugins(mcp_config(), host, connector=connector)

    assert len(plugins) == 1
    assert host.get_capability(CapabilityKind.TOOL, "mcp_demo_echo") is not None
    await plugins[0].close()
    assert connection.closed


async def test_disabled_mcp_is_not_connected() -> None:
    host = PluginHost()
    connector = FakeConnector({"demo": FakeConnection([tool_definition("echo")])})

    plugins = await connect_mcp_plugins(mcp_config(enabled=False), host, connector=connector)

    assert plugins == ()
    assert host.capabilities(CapabilityKind.TOOL) == {}
    assert connector.connected == []


async def test_absent_mcp_config_is_not_connected() -> None:
    assert await connect_mcp_plugins(IntelliAgentConfig(), PluginHost()) == ()


async def test_invalid_mcp_config_is_a_plugin_config_error() -> None:
    config = IntelliAgentConfig(plugins={"mcp": PluginConfig(enabled=True, config={"servers": "not-a-list"})})

    with pytest.raises(PluginConfigError, match="mcp plugin configuration"):
        await connect_mcp_plugins(config, PluginHost())


async def test_connect_failure_wraps_plugin_load_error() -> None:
    connector = FakeConnector({}, connect_errors={"demo": RuntimeError("boom")})
    host = PluginHost()

    with pytest.raises(PluginLoadError, match="boom"):
        await connect_mcp_plugins(mcp_config(), host, connector=connector)

    assert host.capabilities(CapabilityKind.TOOL) == {}


async def test_enabled_mcp_without_discovered_tools_fails_startup() -> None:
    host = PluginHost()

    with pytest.raises(PluginLoadError, match="no MCP tools discovered"):
        await connect_mcp_plugins(mcp_config(servers=[]), host)

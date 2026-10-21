"""Entry Points 发现契约测试：fake 外部插件经 importlib.metadata 路径被发现并加载。"""

from __future__ import annotations

import importlib.metadata
from importlib.metadata import EntryPoint

import pytest

from src.plugins import (
    ApiVersionError,
    CapabilityKind,
    PluginConfigError,
    PluginHost,
    PluginLoadError,
    discovery,
)


def fake_entry_point(name: str, attr: str) -> EntryPoint:
    return EntryPoint(name=name, value=f"tests.plugins.fake_external_plugin:{attr}", group=discovery.ENTRY_POINT_GROUP)


def install_entry_points(monkeypatch: pytest.MonkeyPatch, entry_points: tuple[EntryPoint, ...]) -> list[str]:
    """把 fake entry points 装进 importlib.metadata，并记录被查询的 group。"""
    queried_groups: list[str] = []

    def fake_entry_points_fn(*, group: str) -> tuple[EntryPoint, ...]:
        queried_groups.append(group)
        return entry_points

    monkeypatch.setattr(importlib.metadata, "entry_points", fake_entry_points_fn)
    return queried_groups


class TestDiscovery:
    def test_entry_points_group_is_the_only_third_party_entry(self) -> None:
        assert discovery.ENTRY_POINT_GROUP == "intelliagent.plugins"

    def test_external_plugin_is_discovered_and_loaded_via_entry_points(self, monkeypatch: pytest.MonkeyPatch) -> None:
        queried_groups = install_entry_points(monkeypatch, (fake_entry_point("fake-memory", "FakeExternalPlugin"),))
        host = PluginHost()

        loaded = host.load_entry_points()

        assert queried_groups == ["intelliagent.plugins"]
        assert [item.manifest.name for item in loaded] == ["fake-memory"]
        assert host.get_capability(CapabilityKind.TOOL, "fake-memory.recall") is not None
        assert host.get_capability(CapabilityKind.HOOK, "fake-memory.inject") is not None
        assert "fake-memory" in host.loaded_plugins

    def test_entry_point_factory_function_is_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_entry_points(monkeypatch, (fake_entry_point("fake-memory", "create_fake_external_plugin"),))
        host = PluginHost()

        host.load_entry_points()

        assert host.get_capability(CapabilityKind.TOOL, "fake-memory.recall") is not None

    def test_entry_point_plugin_instance_is_supported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_entry_points(monkeypatch, (fake_entry_point("fake-memory", "fake_external_plugin_instance"),))
        host = PluginHost()

        host.load_entry_points()

        assert host.get_capability(CapabilityKind.HOOK, "fake-memory.inject") is not None

    def test_entry_point_config_is_delivered_by_plugin_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_entry_points(monkeypatch, (fake_entry_point("fake-memory", "FakeExternalPlugin"),))
        host = PluginHost()

        loaded = host.load_entry_points(configs={"fake-memory": {"depth": 2}})

        plugin = loaded[0].plugin
        assert getattr(plugin, "received_config").depth == 2

    def test_invalid_entry_point_config_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_entry_points(monkeypatch, (fake_entry_point("fake-memory", "FakeExternalPlugin"),))
        host = PluginHost()

        with pytest.raises(PluginConfigError) as exc_info:
            host.load_entry_points(configs={"fake-memory": {"depth": "not-an-int"}})

        assert "fake-memory" in str(exc_info.value)
        assert "depth" in str(exc_info.value)

    def test_incompatible_api_version_plugin_is_refused_via_entry_points(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_entry_points(monkeypatch, (fake_entry_point("fake-future", "FakeIncompatiblePlugin"),))
        host = PluginHost()

        with pytest.raises(ApiVersionError):
            host.load_entry_points()

        assert host.get_capability(CapabilityKind.TOOL, "fake-future.run") is None
        assert host.loaded_plugins == {}

    def test_entry_point_load_failure_reports_entry_point_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        entry_point = EntryPoint(
            name="broken-plugin", value="no_such_module_xyz:nothing", group=discovery.ENTRY_POINT_GROUP
        )
        install_entry_points(monkeypatch, (entry_point,))
        host = PluginHost()

        with pytest.raises(PluginLoadError) as exc_info:
            host.load_entry_points()

        assert "broken-plugin" in str(exc_info.value)

    @pytest.mark.parametrize("attr", ["NotAPlugin", "not_a_plugin", "UnrelatedFactory"])
    def test_entry_point_resolving_to_non_plugin_is_rejected(self, monkeypatch: pytest.MonkeyPatch, attr: str) -> None:
        install_entry_points(monkeypatch, (fake_entry_point("broken-plugin", attr),))
        host = PluginHost()

        with pytest.raises(PluginLoadError) as exc_info:
            host.load_entry_points()

        message = str(exc_info.value)
        assert "broken-plugin" in message
        assert "fake-memory" not in host.loaded_plugins

    def test_no_entry_points_yields_empty_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_entry_points(monkeypatch, ())
        host = PluginHost()

        assert host.load_entry_points() == []

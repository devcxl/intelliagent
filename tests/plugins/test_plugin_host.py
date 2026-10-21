"""PluginHost 契约测试：加载、api_version 拒绝、配置 schema 校验、能力注册冲突。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.plugins import (
    ApiVersionError,
    CapabilityConflictError,
    CapabilityDeclaration,
    CapabilityKind,
    PluginConfigError,
    PluginHost,
    PluginLoadError,
)
from tests.plugins.fakes import FakePlugin, FakeToolConfig, build_manifest, single_provider


class TestPluginLoading:
    def test_load_registers_declared_capabilities(self) -> None:
        host = PluginHost()
        manifest = build_manifest(
            capabilities=(
                CapabilityDeclaration(kind=CapabilityKind.TOOL, name="fake.echo"),
                CapabilityDeclaration(kind=CapabilityKind.HOOK, name="fake.inject"),
            )
        )
        tool_provider = single_provider()
        hook_provider = single_provider()
        plugin = FakePlugin(
            manifest,
            providers={
                (CapabilityKind.TOOL, "fake.echo"): tool_provider,
                (CapabilityKind.HOOK, "fake.inject"): hook_provider,
            },
        )

        loaded = host.load(plugin)

        assert loaded.manifest is manifest
        assert loaded.plugin is plugin
        assert host.get_capability(CapabilityKind.TOOL, "fake.echo") is tool_provider
        assert host.get_capability(CapabilityKind.HOOK, "fake.inject") is hook_provider
        assert host.capabilities(CapabilityKind.TOOL) == {"fake.echo": tool_provider}
        assert host.loaded_plugins["fake-tool"] is loaded

    def test_querying_missing_capability_returns_none(self) -> None:
        host = PluginHost()
        host.load(FakePlugin())

        assert host.get_capability(CapabilityKind.TOOL, "missing") is None

    def test_loading_same_plugin_name_twice_is_rejected(self) -> None:
        host = PluginHost()
        host.load(FakePlugin())

        with pytest.raises(PluginLoadError) as exc_info:
            host.load(
                FakePlugin(build_manifest(capabilities=(CapabilityDeclaration(kind=CapabilityKind.HOOK, name="h"),)))
            )

        message = str(exc_info.value)
        assert "fake-tool" in message
        assert "already loaded" in message

    def test_plugin_without_manifest_is_rejected(self) -> None:
        host = PluginHost()

        with pytest.raises(PluginLoadError):
            host.load(object())  # type: ignore[arg-type]


class TestApiVersionGate:
    def test_compatible_api_version_loads(self) -> None:
        host = PluginHost()
        loaded = host.load(FakePlugin(build_manifest(api_version=PluginHost.SUPPORTED_API_VERSIONS.start)))

        assert loaded.manifest.api_version == PluginHost.SUPPORTED_API_VERSIONS.start

    def test_incompatible_api_version_is_refused_with_diagnosable_error(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(build_manifest(api_version=99))

        with pytest.raises(ApiVersionError) as exc_info:
            host.load(plugin)

        message = str(exc_info.value)
        assert "fake-tool" in message
        assert "99" in message

    def test_refused_plugin_leaves_no_capabilities_registered(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(build_manifest(api_version=99))

        with pytest.raises(ApiVersionError):
            host.load(plugin)

        assert host.get_capability(CapabilityKind.TOOL, "fake.echo") is None
        assert host.loaded_plugins == {}


class TestPluginConfigSchema:
    def test_valid_config_is_validated_and_passed_to_plugin(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(build_manifest(config_schema=FakeToolConfig))

        loaded = host.load(plugin, {"limit": 3, "path": "/tmp/x"})

        assert isinstance(plugin.received_config, FakeToolConfig)
        assert plugin.received_config.limit == 3
        assert loaded.config == FakeToolConfig(limit=3, path="/tmp/x")

    def test_invalid_config_error_names_plugin_and_field(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(build_manifest(config_schema=FakeToolConfig))

        with pytest.raises(PluginConfigError) as exc_info:
            host.load(plugin, {"limit": "not-an-int"})

        message = str(exc_info.value)
        assert "fake-tool" in message
        assert "limit" in message

    def test_unknown_config_field_error_names_plugin_and_field(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(build_manifest(config_schema=FakeToolConfig))

        with pytest.raises(PluginConfigError) as exc_info:
            host.load(plugin, {"limit": 1, "unknown_key": True})

        message = str(exc_info.value)
        assert "fake-tool" in message
        assert "unknown_key" in message

    def test_config_without_declared_schema_is_rejected(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(build_manifest(config_schema=None))

        with pytest.raises(PluginConfigError) as exc_info:
            host.load(plugin, {"limit": 1})

        message = str(exc_info.value)
        assert "fake-tool" in message

    def test_refused_config_leaves_no_capabilities_registered(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(build_manifest(config_schema=FakeToolConfig))

        with pytest.raises(PluginConfigError):
            host.load(plugin, {"limit": "not-an-int"})

        assert host.get_capability(CapabilityKind.TOOL, "fake.echo") is None


class TestCapabilityContract:
    def test_cross_plugin_capability_conflict_is_rejected_and_names_both_plugins(self) -> None:
        host = PluginHost()
        host.load(FakePlugin(build_manifest(name="core-tools")))
        conflicting = FakePlugin(
            build_manifest(
                name="other-tools",
                capabilities=(
                    CapabilityDeclaration(kind=CapabilityKind.HOOK, name="other.inject"),
                    CapabilityDeclaration(kind=CapabilityKind.TOOL, name="fake.echo"),
                ),
            ),
            providers={
                (CapabilityKind.HOOK, "other.inject"): single_provider(),
                (CapabilityKind.TOOL, "fake.echo"): single_provider(),
            },
        )

        with pytest.raises(CapabilityConflictError) as exc_info:
            host.load(conflicting)

        message = str(exc_info.value)
        assert "core-tools" in message
        assert "other-tools" in message
        assert "fake.echo" in message

    def test_conflicting_plugin_registers_nothing(self) -> None:
        host = PluginHost()
        host.load(FakePlugin(build_manifest(name="core-tools")))
        conflicting = FakePlugin(
            build_manifest(
                name="other-tools",
                capabilities=(
                    CapabilityDeclaration(kind=CapabilityKind.HOOK, name="other.inject"),
                    CapabilityDeclaration(kind=CapabilityKind.TOOL, name="fake.echo"),
                ),
            ),
            providers={
                (CapabilityKind.HOOK, "other.inject"): single_provider(),
                (CapabilityKind.TOOL, "fake.echo"): single_provider(),
            },
        )

        with pytest.raises(CapabilityConflictError):
            host.load(conflicting)

        assert host.get_capability(CapabilityKind.HOOK, "other.inject") is None
        assert "other-tools" not in host.loaded_plugins

    def test_registering_undeclared_capability_is_rejected(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(
            providers={
                (CapabilityKind.TOOL, "fake.echo"): single_provider(),
                (CapabilityKind.HOOK, "fake.undeclared"): single_provider(),
            }
        )

        with pytest.raises(PluginLoadError) as exc_info:
            host.load(plugin)

        message = str(exc_info.value)
        assert "fake-tool" in message
        assert "fake.undeclared" in message

    def test_missing_declared_capability_is_rejected(self) -> None:
        host = PluginHost()
        plugin = FakePlugin(providers={})

        with pytest.raises(PluginLoadError) as exc_info:
            host.load(plugin)

        message = str(exc_info.value)
        assert "fake-tool" in message
        assert "fake.echo" in message

    def test_duplicate_registration_within_one_plugin_is_rejected(self) -> None:
        host = PluginHost()
        manifest = build_manifest()

        class DoubleRegisterPlugin:
            def __init__(self) -> None:
                self.manifest = manifest

            def register(self, registrar: object, config: object) -> None:
                registrar.register(CapabilityKind.TOOL, "fake.echo", object())  # type: ignore[attr-defined]
                registrar.register(CapabilityKind.TOOL, "fake.echo", object())  # type: ignore[attr-defined]

        with pytest.raises(CapabilityConflictError) as exc_info:
            host.load(DoubleRegisterPlugin())  # type: ignore[arg-type]

        message = str(exc_info.value)
        assert "fake-tool" in message
        assert "fake.echo" in message


class TestManifestRejectedAtConstruction:
    def test_invalid_manifest_is_rejected_before_load(self) -> None:
        with pytest.raises(ValidationError):
            build_manifest(name="Invalid Name")

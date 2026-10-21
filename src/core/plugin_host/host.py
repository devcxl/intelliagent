"""PluginHost：插件加载、api_version 门禁、配置 schema 校验与能力提交（ADR 0007）。"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, ClassVar, NamedTuple

from pydantic import BaseModel, ValidationError

from src.core.plugin_host.discovery import ENTRY_POINT_GROUP, discover_entry_points, resolve_plugin
from src.core.plugin_host.errors import ApiVersionError, CapabilityConflictError, PluginConfigError, PluginLoadError
from src.core.plugin_host.manifest import CapabilityKind, Manifest
from src.core.plugin_host.protocol import Plugin
from src.core.plugin_host.registry import CapabilityKey, CapabilityRegistrar, CapabilityRegistry


class LoadedPlugin(NamedTuple):
    """一个已通过门禁并完成能力注册的插件。"""

    manifest: Manifest
    plugin: Plugin
    config: BaseModel | None


class PluginHost:
    """插件宿主：只加载 api_version 兼容的插件，能力名冲突拒绝并报可诊断错误。"""

    SUPPORTED_API_VERSIONS: ClassVar[range] = range(1, 2)

    def __init__(self, registry: CapabilityRegistry | None = None) -> None:
        self._registry = registry if registry is not None else CapabilityRegistry()
        self._plugins: dict[str, LoadedPlugin] = {}

    @property
    def loaded_plugins(self) -> Mapping[str, LoadedPlugin]:
        """已加载插件，按插件名索引。"""
        return MappingProxyType(self._plugins)

    def load(self, plugin: Plugin, config: Mapping[str, Any] | None = None) -> LoadedPlugin:
        """加载单个插件：api_version 门禁 → 配置校验 → 能力注册 → 提交。

        内置插件与外部插件走同一路径，区别仅在发现方式。
        """
        manifest, validated_config, pending = self._prepare(plugin, config)
        self._registry.commit(manifest.name, pending)
        loaded = LoadedPlugin(manifest=manifest, plugin=plugin, config=validated_config)
        self._plugins[manifest.name] = loaded
        return loaded

    def load_entry_points(
        self,
        configs: Mapping[str, Mapping[str, Any]] | None = None,
        *,
        group: str = ENTRY_POINT_GROUP,
    ) -> list[LoadedPlugin]:
        """发现并加载 Entry Points group 下的全部外部插件（两阶段提交）。

        先完成全部插件的门禁、配置校验与能力登记，并做跨批次冲突预检；
        任一插件失败即整体拒绝且零副作用（无部分加载）。全部通过后统一落账。

        configs 按插件名索引各插件的配置段（来自 intelliagent.yaml 的 plugins: 段）。
        """
        prepared: list[tuple[Plugin, Manifest, BaseModel | None, Mapping[CapabilityKey, object]]] = []
        for entry_point in discover_entry_points(group):
            plugin = resolve_plugin(entry_point)
            config = configs.get(plugin.manifest.name) if configs is not None else None
            manifest, validated_config, pending = self._prepare(plugin, config)
            prepared.append((plugin, manifest, validated_config, pending))
        self._require_no_batch_conflicts(prepared)
        loaded: list[LoadedPlugin] = []
        for plugin, manifest, validated_config, pending in prepared:
            self._registry.commit(manifest.name, pending)
            item = LoadedPlugin(manifest=manifest, plugin=plugin, config=validated_config)
            self._plugins[manifest.name] = item
            loaded.append(item)
        return loaded

    def get_capability(self, kind: CapabilityKind, name: str) -> object | None:
        """查询能力提供者；不存在返回 None。"""
        return self._registry.get(kind, name)

    def capabilities(self, kind: CapabilityKind) -> Mapping[str, object]:
        """查询某一能力类型的全部提供者。"""
        return self._registry.get_all(kind)

    def _require_manifest(self, plugin: Plugin) -> Manifest:
        manifest = getattr(plugin, "manifest", None)
        if not isinstance(manifest, Manifest):
            raise PluginLoadError(
                f"plugin '{type(plugin).__name__}' must expose a Manifest as its 'manifest' attribute"
            )
        return manifest

    def _require_compatible_api_version(self, manifest: Manifest) -> None:
        if manifest.api_version not in self.SUPPORTED_API_VERSIONS:
            supported = self.SUPPORTED_API_VERSIONS
            raise ApiVersionError(
                f"plugin '{manifest.name}' declares api_version {manifest.api_version}, "
                f"but this host supports api_version {supported.start}..{supported.stop - 1}; refusing to load"
            )

    def _validate_config(self, manifest: Manifest, config: Mapping[str, Any] | None) -> BaseModel | None:
        values = dict(config or {})
        schema = manifest.config_schema
        if schema is None:
            if values:
                fields = ", ".join(sorted(values))
                raise PluginConfigError(
                    f"plugin '{manifest.name}' declares no config schema but received configuration fields: {fields}"
                )
            return None
        try:
            return schema.model_validate(values)
        except ValidationError as exc:
            details = "; ".join(
                f"field '{'.'.join(str(part) for part in error['loc'])}': {error['msg']}" for error in exc.errors()
            )
            raise PluginConfigError(f"plugin '{manifest.name}' configuration is invalid: {details}") from exc

    def _prepare(
        self, plugin: Plugin, config: Mapping[str, Any] | None
    ) -> tuple[Manifest, BaseModel | None, Mapping[CapabilityKey, object]]:
        """门禁 + 配置校验 + 能力登记（不落账），供 load 与 load_entry_points 复用。"""
        manifest = self._require_manifest(plugin)
        if manifest.name in self._plugins:
            raise PluginLoadError(f"plugin '{manifest.name}' is already loaded")
        self._require_compatible_api_version(manifest)
        validated_config = self._validate_config(manifest, config)
        registrar = CapabilityRegistrar(manifest.name, manifest)
        plugin.register(registrar, validated_config)
        self._require_complete(manifest, registrar)
        return manifest, validated_config, registrar.pending

    def _require_no_batch_conflicts(
        self, prepared: list[tuple[Plugin, Manifest, BaseModel | None, Mapping[CapabilityKey, object]]]
    ) -> None:
        """跨批次冲突预检：批次内互相冲突、或与已加载能力冲突时整体拒绝。"""
        seen: dict[CapabilityKey, str] = {}
        for _plugin, manifest, _config, pending in prepared:
            for kind, name in pending:
                key: CapabilityKey = (kind, name)
                if key in seen:
                    raise CapabilityConflictError(
                        f"capability '{kind.value}:{name}' is already registered by plugin '{seen[key]}' "
                        f"(requested by plugin '{manifest.name}')"
                    )
                owner = self._registry.owner(kind, name)
                if owner is not None:
                    raise CapabilityConflictError(
                        f"capability '{kind.value}:{name}' is already registered by plugin '{owner}' "
                        f"(requested by plugin '{manifest.name}')"
                    )
                seen[key] = manifest.name

    def _require_complete(self, manifest: Manifest, registrar: CapabilityRegistrar) -> None:
        pending = registrar.pending
        for declaration in manifest.capabilities:
            key: CapabilityKey = (declaration.kind, declaration.name)
            if key not in pending:
                raise PluginLoadError(
                    f"plugin '{manifest.name}' did not register declared capability "
                    f"'{declaration.kind.value}:{declaration.name}'"
                )

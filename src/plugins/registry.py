"""Capability 注册表：能力 (kind, name) 全局唯一，冲突拒绝并报可诊断错误。"""

from __future__ import annotations

from collections.abc import Mapping

from src.plugins.errors import CapabilityConflictError, PluginLoadError
from src.plugins.manifest import CapabilityKind, Manifest

CapabilityKey = tuple[CapabilityKind, str]


class CapabilityRegistry:
    """能力名到提供者的映射，记录每个能力的归属插件用于冲突诊断。"""

    def __init__(self) -> None:
        self._entries: dict[CapabilityKind, dict[str, tuple[str, object]]] = {kind: {} for kind in CapabilityKind}

    def register(self, plugin_name: str, kind: CapabilityKind, name: str, provider: object) -> None:
        """注册单个能力；(kind, name) 已被占用时抛 CapabilityConflictError。"""
        self.commit(plugin_name, {(kind, name): provider})

    def commit(self, plugin_name: str, entries: Mapping[CapabilityKey, object]) -> None:
        """原子批量注册：先整体检查冲突，全部可用才写入。"""
        for kind, name in entries:
            self._require_free(plugin_name, kind, name)
        for (kind, name), provider in entries.items():
            self._entries[kind][name] = (plugin_name, provider)

    def get(self, kind: CapabilityKind, name: str) -> object | None:
        """查询能力提供者；不存在返回 None。"""
        entry = self._entries[kind].get(name)
        return entry[1] if entry is not None else None

    def get_all(self, kind: CapabilityKind) -> Mapping[str, object]:
        """查询某一能力类型的全部提供者。"""
        return {name: provider for name, (_, provider) in self._entries[kind].items()}

    def _require_free(self, plugin_name: str, kind: CapabilityKind, name: str) -> None:
        entry = self._entries[kind].get(name)
        if entry is not None:
            owner, _ = entry
            raise CapabilityConflictError(
                f"capability '{kind.value}:{name}' is already registered by plugin '{owner}' "
                f"(requested by plugin '{plugin_name}')"
            )


class CapabilityRegistrar:
    """宿主交给单个插件的注册句柄（CONTEXT 术语：Capability）。

    只接受 Manifest 已声明的能力，注册结果随插件加载一次性提交到 CapabilityRegistry。
    """

    def __init__(self, plugin_name: str, manifest: Manifest) -> None:
        self._plugin_name = plugin_name
        self._declared: set[CapabilityKey] = {(item.kind, item.name) for item in manifest.capabilities}
        self._pending: dict[CapabilityKey, object] = {}

    def register(self, kind: CapabilityKind, name: str, provider: object) -> None:
        """登记一个待提交能力；未声明或重复登记都会被拒绝。"""
        key = (kind, name)
        if key not in self._declared:
            raise PluginLoadError(
                f"plugin '{self._plugin_name}' registered capability '{kind.value}:{name}' "
                f"that is not declared in its Manifest"
            )
        if key in self._pending:
            raise CapabilityConflictError(
                f"plugin '{self._plugin_name}' registered capability '{kind.value}:{name}' more than once"
            )
        self._pending[key] = provider

    @property
    def pending(self) -> Mapping[CapabilityKey, object]:
        """当前已登记、待提交的能力。"""
        return dict(self._pending)

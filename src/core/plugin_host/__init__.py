"""插件宿主与契约（ADR 0007）：Manifest、Plugin Protocol、Entry Points 发现、Capability 注册表。"""

from src.core.plugin_host.discovery import ENTRY_POINT_GROUP, discover_entry_points, resolve_plugin
from src.core.plugin_host.errors import (
    ApiVersionError,
    CapabilityConflictError,
    PluginConfigError,
    PluginError,
    PluginLoadError,
)
from src.core.plugin_host.host import LoadedPlugin, PluginHost
from src.core.plugin_host.manifest import CapabilityDeclaration, CapabilityKind, Manifest
from src.core.plugin_host.protocol import Plugin
from src.core.plugin_host.registry import CapabilityRegistrar, CapabilityRegistry

__all__ = [
    "ENTRY_POINT_GROUP",
    "ApiVersionError",
    "CapabilityConflictError",
    "CapabilityDeclaration",
    "CapabilityKind",
    "CapabilityRegistrar",
    "CapabilityRegistry",
    "LoadedPlugin",
    "Manifest",
    "Plugin",
    "PluginConfigError",
    "PluginError",
    "PluginHost",
    "PluginLoadError",
    "discover_entry_points",
    "resolve_plugin",
]

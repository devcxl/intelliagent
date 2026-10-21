"""插件宿主与契约（ADR 0007）：Manifest、Plugin Protocol、Entry Points 发现、Capability 注册表。"""

from src.plugins.discovery import ENTRY_POINT_GROUP, discover_entry_points, resolve_plugin
from src.plugins.errors import (
    ApiVersionError,
    CapabilityConflictError,
    PluginConfigError,
    PluginError,
    PluginLoadError,
)
from src.plugins.host import LoadedPlugin, PluginHost
from src.plugins.manifest import CapabilityDeclaration, CapabilityKind, Manifest
from src.plugins.protocol import Plugin
from src.plugins.registry import CapabilityRegistrar, CapabilityRegistry

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

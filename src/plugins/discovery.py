"""Entry Points 发现：外部插件的唯一发现入口（CONTEXT 术语：Entry Point）。"""

from __future__ import annotations

import importlib.metadata
from importlib.metadata import EntryPoint

from src.plugins.errors import PluginLoadError
from src.plugins.manifest import Manifest
from src.plugins.protocol import Plugin

ENTRY_POINT_GROUP = "intelliagent.plugins"


def discover_entry_points(group: str = ENTRY_POINT_GROUP) -> tuple[EntryPoint, ...]:
    """枚举指定 group 下的全部 Entry Points。"""
    return tuple(importlib.metadata.entry_points(group=group))


def resolve_plugin(entry_point: EntryPoint) -> Plugin:
    """把 Entry Point 解析为 Plugin 实例。

    Entry Point 的值指向 Plugin 实例，或零参可调用对象（工厂函数 / Plugin 类）。
    """
    try:
        target = entry_point.load()
    except Exception as exc:
        raise PluginLoadError(
            f"entry point '{entry_point.name}' (group '{entry_point.group}') failed to load: {exc}"
        ) from exc

    if callable(target):
        try:
            plugin = target()
        except Exception as exc:
            raise PluginLoadError(
                f"entry point '{entry_point.name}' (group '{entry_point.group}') factory failed: {exc}"
            ) from exc
    else:
        plugin = target

    if not isinstance(plugin, Plugin) or not isinstance(getattr(plugin, "manifest", None), Manifest):
        raise PluginLoadError(
            f"entry point '{entry_point.name}' (group '{entry_point.group}') must resolve to a Plugin instance "
            f"or a zero-argument factory returning one, got {type(plugin).__name__}"
        )
    return plugin

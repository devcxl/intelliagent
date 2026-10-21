"""无头运行时装配：intelliagent.yaml → PluginHost（内置 + 外部插件）→ Engine（ADR 0008 / ADR 0009）。

装配顺序：load_config（YAML + {env:} 插值）→ 内置插件（basic-tools、storage）→ Entry Points 外部插件
→ 无 PERMISSION 能力则按 ADR 0008 发安全警告 → Engine.from_host。plugins: 段的 enabled: false
对内置与外部插件统一生效，其余条目以 config 传给对应插件。
"""

from __future__ import annotations

from typing import TextIO

from src.config.yaml_config import IntelliAgentConfig
from src.core.plugin_host import CapabilityKind, Plugin, PluginHost, discover_entry_points, resolve_plugin
from src.llm.litellm_client import LiteLLMClient
from src.llm.stream import LLMClient
from src.plugins.basic_tools import BasicToolsPlugin
from src.plugins.storage import StoragePlugin

BUILT_IN_PLUGINS: tuple[Plugin, ...] = (BasicToolsPlugin(), StoragePlugin())

PERMISSION_WARNING = (
    "警告: 未安装 permission 插件，所有工具调用将不经确认直接执行（ADR 0008 默认安全姿态）。"
    "面向不可信任务使用前，请先安装 permission 插件。\n"
)


def create_llm_client() -> LLMClient:
    """默认 LLM 客户端（litellm 统一接入）；测试经 monkeypatch 替换为 fake。"""
    return LiteLLMClient()


def build_host(config: IntelliAgentConfig) -> PluginHost:
    """按配置组装 PluginHost：内置插件与 Entry Points 外部插件走同一加载路径。"""
    host = PluginHost()
    for plugin in BUILT_IN_PLUGINS:
        entry = config.plugins.get(plugin.manifest.name)
        if entry is not None and not entry.enabled:
            continue
        host.load(plugin, entry.config if entry is not None else None)
    for entry_point in discover_entry_points():
        plugin = resolve_plugin(entry_point)
        entry = config.plugins.get(plugin.manifest.name)
        if entry is not None and not entry.enabled:
            continue
        host.load(plugin, entry.config if entry is not None else None)
    return host


def warn_missing_permission_plugin(host: PluginHost, stderr: TextIO) -> None:
    """ADR 0008 姿态：无 PERMISSION 能力提供者时内核不做任何检查，必须显著警告。"""
    if not host.capabilities(CapabilityKind.PERMISSION):
        stderr.write(PERMISSION_WARNING)
        stderr.flush()

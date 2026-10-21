"""插件化运行时装配（新架构组合根）：intelliagent.yaml → PluginHost → Engine。

装配顺序：load_config（YAML + {env:} 插值）→ 内置插件 → Entry Points 外部插件。
plugins: 段的 enabled: false 对内置与外部插件统一生效，其余条目以 config 传给对应插件。

本模块是 headless 与 TUI 共用的装配根（AGENTS.md：composition root 归 runtime 层，
避免每个前端各建装配逻辑）；旧 src/runtime/assembly.py 随 #64 删除。
"""

from __future__ import annotations

import re
from typing import TextIO

from src.config.yaml_config import IntelliAgentConfig
from src.core.plugin_host import CapabilityKind, Plugin, PluginHost, discover_entry_points, resolve_plugin
from src.llm.client import ProviderClient
from src.llm.protocols.litellm_adapter import LitellmAdapter
from src.llm.stream import LLMClient
from src.plugins.basic_tools import BasicToolsPlugin
from src.plugins.storage import StoragePlugin

BUILT_IN_PLUGINS: tuple[Plugin, ...] = (BasicToolsPlugin(), StoragePlugin())

PERMISSION_WARNING = (
    "警告: 未安装 permission 插件，本次运行的工具调用将不经确认直接执行（ADR 0008 默认安全姿态）。"
    "面向不可信任务使用前，请先安装 permission 插件。\n"
)

# 敏感值脱敏：错误文本经此输出，避免 {env:} 插值后的密钥经异常/诊断泄出（AGENTS.md）。
_SECRET_PATTERN = re.compile(r"(?i)(sk-[A-Za-z0-9]{8,})|([?&](?:api[_-]?key|token|secret)=)[^&\s\"']+")


def redact_secrets(text: str) -> str:
    """把疑似密钥的值替换为占位符；用于一切面向用户/日志的诊断输出。"""

    def _sub(match: re.Match[str]) -> str:
        return "<redacted>" if match.group(1) else f"{match.group(2)}<redacted>"

    return _SECRET_PATTERN.sub(_sub, text)


def create_llm_client() -> LLMClient:
    """默认 LLM 客户端（litellm 临时适配器）；测试经 monkeypatch 替换为 fake。"""
    return ProviderClient(LitellmAdapter())


def build_host(config: IntelliAgentConfig) -> PluginHost:
    """按配置组装 PluginHost：内置插件与 Entry Points 外部插件走同一加载路径。"""
    host = PluginHost()
    for plugin, entry_config in _iter_plugin_sources(config):
        host.load(plugin, entry_config)
    return host


def _iter_plugin_sources(config: IntelliAgentConfig):
    """内置与外部插件统一的启用/配置裁决（消除两段重复加载循环）。"""
    for plugin in BUILT_IN_PLUGINS:
        entry = config.plugins.get(plugin.manifest.name)
        if entry is not None and not entry.enabled:
            continue
        yield plugin, entry.config if entry is not None else None
    for entry_point in discover_entry_points():
        plugin = resolve_plugin(entry_point)
        entry = config.plugins.get(plugin.manifest.name)
        if entry is not None and not entry.enabled:
            continue
        yield plugin, entry.config if entry is not None else None


def warn_missing_permission_plugin(host: PluginHost, stderr: TextIO) -> None:
    """ADR 0008 姿态：本次运行有工具（可能产生副作用）且无 PERMISSION 能力时显著警告。

    零工具的 run 没有可拦截的动作，不警告（US45：a run that would *need* permission）。
    """
    if host.capabilities(CapabilityKind.TOOL) and not host.capabilities(CapabilityKind.PERMISSION):
        stderr.write(PERMISSION_WARNING)
        stderr.flush()

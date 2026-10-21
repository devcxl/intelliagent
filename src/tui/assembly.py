"""TUI 组装：intelliagent.yaml → 引擎 + TUI。

装配复用 src/runtime/plugin_assembly（共用组合根：内置 + Entry Points 插件、
plugins: 裁决、ADR 0008 permission 警告），本模块只保留 TUI 前端接线。
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.config.yaml_config import ConfigError, IntelliAgentConfig, load_config
from src.core.agent_events import EventSink
from src.core.engine import Engine
from src.runtime.plugin_assembly import build_host, create_llm_client, warn_missing_permission_plugin
from src.tui.app import IntelliAgentApp, TaskRunner


def build_app(config_path: str | Path | None = None) -> IntelliAgentApp:
    """从 intelliagent.yaml 组装可运行的 TUI：配置 → PluginHost → 引擎 → 事件流接线。

    Args:
        config_path: intelliagent.yaml 路径，缺省读取当前目录。

    Returns:
        已接好引擎的 TUI 应用，调用 .run() 即启动。
    """
    config = load_config(config_path)
    model = _require_default_model(config)
    cwd = Path(config.workspace.dir).resolve()
    host = build_host(config)
    llm = create_llm_client(config)
    warn_missing_permission_plugin(host, sys.stderr)

    def runner_factory(sink: EventSink) -> TaskRunner:
        return Engine.from_host(host, llm=llm, model=model, sink=sink)

    return IntelliAgentApp(runner_factory=runner_factory, model=model, cwd=cwd)


def _require_default_model(config: IntelliAgentConfig) -> str:
    if config.default_model is None:
        raise ConfigError("default_model: 未配置模型（intelliagent.yaml 需要 default_model 与 providers 段）")
    return config.default_model

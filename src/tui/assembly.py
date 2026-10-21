"""最小组装：intelliagent.yaml → 引擎 + TUI（issue #60 无头模式组装未合并前的过渡实现）。

#60 的无头模式 runtime 组装落地后，本模块改为复用其组装，只保留 TUI 前端接线。
"""

from __future__ import annotations

from pathlib import Path

from src.config.yaml_config import ConfigError, IntelliAgentConfig, load_config
from src.core.agent_events import EventSink
from src.core.engine import Engine
from src.core.plugin_host import PluginHost
from src.llm.litellm_client import LiteLLMClient
from src.plugins.basic_tools import BasicToolsPlugin
from src.tui.app import IntelliAgentApp, TaskRunner


def build_app(config_path: str | Path | None = None) -> IntelliAgentApp:
    """从 intelliagent.yaml 组装可运行的 TUI：配置 → 引擎（含内置工具）→ 事件流接线。

    Args:
        config_path: intelliagent.yaml 路径，缺省读取当前目录。

    Returns:
        已接好引擎的 TUI 应用，调用 .run() 即启动。
    """
    config = load_config(config_path)
    model = _require_model(config)
    cwd = Path(config.workspace.dir).resolve()

    def runner_factory(sink: EventSink) -> TaskRunner:
        host = PluginHost()
        host.load(BasicToolsPlugin())
        return Engine.from_host(host, llm=LiteLLMClient(), model=model, sink=sink)

    return IntelliAgentApp(runner_factory=runner_factory, model=model, cwd=cwd)


def _require_model(config: IntelliAgentConfig) -> str:
    if config.model is None:
        raise ConfigError("model: 未配置模型（intelliagent.yaml 需要 model 字段，如 openai/gpt-4o）")
    return config.model

"""TUI 组装：intelliagent.yaml → 引擎 + TUI。

装配复用 src/runtime/plugin_assembly（共用组合根：内置 + Entry Points 插件、
plugins: 裁决、ADR 0008 permission 警告），本模块只保留 TUI 前端接线。
"""

from __future__ import annotations

from pathlib import Path

from src.config.yaml_config import ConfigError, IntelliAgentConfig, load_config
from src.core.agent_events import EventSink
from src.runtime.engine_runtime import EngineRuntime, build_engine_runtime
from src.runtime.plugin_assembly import (
    build_host,
    connect_mcp_plugins,
    create_llm_client,
    permission_warning,
)
from src.tui.app import IntelliAgentApp, TaskRunner

TUI_CONVERSATION_ID = "tui"
"""TUI 固定续接的会话根 id：同一数据库只保留一段交互式会话。"""


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
    llm = create_llm_client(config)
    runtimes: list[EngineRuntime] = []
    notices: list[str] = []

    async def runner_factory(sink: EventSink) -> TaskRunner:
        host = build_host(config)
        mcp_plugins = await connect_mcp_plugins(config, host)
        try:
            warning = permission_warning(host)
            if warning is not None:
                notices.append(warning.strip())
            runtime = build_engine_runtime(
                config,
                host,
                llm,
                model,
                sink,
                conversation_id=TUI_CONVERSATION_ID,
                resume=True,
                closers=tuple(plugin.close for plugin in mcp_plugins),
            )
        except BaseException:
            for plugin in mcp_plugins:
                try:
                    await plugin.close()
                except Exception:
                    pass
            raise
        runtimes.append(runtime)
        return runtime.engine

    async def close_runtime() -> None:
        for runtime in runtimes:
            await runtime.close()

    return IntelliAgentApp(
        runner_factory=runner_factory,
        model=model,
        cwd=cwd,
        on_close=close_runtime,
        startup_notices=notices,
    )


def _require_default_model(config: IntelliAgentConfig) -> str:
    if config.default_model is None:
        raise ConfigError("default_model: 未配置模型（intelliagent.yaml 需要 default_model 与 providers 段）")
    return config.default_model

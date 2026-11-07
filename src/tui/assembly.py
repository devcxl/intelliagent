"""TUI 组装：intelliagent.yaml → 引擎 + TUI，并持有会话切换所需的共享资源（ADR 0013）。

装配复用 src/runtime/plugin_assembly（共用组合根：内置 + Entry Points 插件、plugins: 裁决、
ADR 0008 permission 警告），本模块只保留 TUI 前端接线。

关键约束：PluginHost 与 MCP 连接只建一次，切换会话只换 EngineRuntime——重建 host 会重连
MCP，代价远高于收益。会话选择（-c / -s / 缺省新建）在初始装配时解析一次，之后由
`/resume` 与 `/new` 驱动。
"""

from __future__ import annotations

from pathlib import Path

from src.config.yaml_config import ConfigError, IntelliAgentConfig, load_config
from src.runtime.tui_session_controller import TuiSessionController
from src.tui.app import IntelliAgentApp


def build_app(
    config_path: str | Path | None = None,
    *,
    resume_last: bool = False,
    conversation_id: str | None = None,
) -> IntelliAgentApp:
    """从 intelliagent.yaml 组装可运行的 TUI：配置 → PluginHost → 引擎 → 事件流接线。

    Args:
        config_path: intelliagent.yaml 路径，缺省读取当前目录。
        resume_last: 恢复本目录最近创建的会话（``-c``）。
        conversation_id: 打开指定会话（``-s``）；不存在时启动失败。

    Returns:
        已接好引擎的 TUI 应用，调用 .run() 即启动。
    """
    config = load_config(config_path)
    model = _require_default_model(config)
    cwd = Path(config.workspace.dir).resolve()
    notices: list[str] = []
    controller = TuiSessionController(
        config,
        cwd,
        model,
        _model_display_name(config, model),
        resume_last=resume_last,
        conversation_id=conversation_id,
        notices=notices,
    )
    return IntelliAgentApp(
        runner_factory=controller.initial_runner,
        model=controller.model_label,
        cwd=cwd,
        on_close=controller.close,
        startup_notices=notices,
        session_controller=controller,
    )


def _require_default_model(config: IntelliAgentConfig) -> str:
    if config.default_model is None:
        raise ConfigError("default_model: 未配置模型（intelliagent.yaml 需要 default_model 与 providers 段）")
    return config.default_model


def _model_display_name(config: IntelliAgentConfig, model_ref: str) -> str:
    """状态栏展示名：优先模型条目 name，缺失时回退 provider/model-id。"""
    provider_name, _, model_id = model_ref.partition("/")
    provider = config.providers.get(provider_name)
    model = provider.models.get(model_id) if provider is not None else None
    if model is not None and model.name:
        return model.name
    return model_ref

"""最小组装：intelliagent.yaml → 引擎 + TUI（issue #60 无头模式组装未合并前的过渡实现）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.yaml_config import ConfigError
from src.core.engine import Engine
from src.tui.app import IntelliAgentApp
from src.tui.assembly import build_app
from src.tui.status_bar import StatusBar
from tests.tui.conftest import ScriptedRunner

_DEFAULT_CONFIG = (
    "default_model: fake/model\n"
    "providers:\n"
    "  fake:\n"
    "    type: openai-compatible\n"
    "    api: http://127.0.0.1:9/v1\n"
    "    models:\n"
    "      model: {}\n"
)


def _write_config(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "intelliagent.yaml"
    config.write_text(body, encoding="utf-8")
    return config


async def test_build_app_wires_engine_as_task_runner(tmp_path: Path) -> None:
    config = _write_config(tmp_path, _DEFAULT_CONFIG + "workspace:\n  dir: /work/project\n")
    app = build_app(config)
    async with app.run_test():
        assert isinstance(app.task_runner, Engine)


async def test_status_bar_shows_configured_cwd_and_model(tmp_path: Path) -> None:
    config = _write_config(tmp_path, _DEFAULT_CONFIG + "workspace:\n  dir: /work/project\n")
    app = build_app(config)
    async with app.run_test() as pilot:
        bar = pilot.app.query_one(StatusBar)
        assert "/work/project" in bar.text
        assert "fake/model" in bar.text


async def test_status_bar_shows_model_display_name(tmp_path: Path) -> None:
    config = _write_config(
        tmp_path,
        "default_model: fake/model\n"
        "providers:\n"
        "  fake:\n"
        "    type: openai-compatible\n"
        "    api: http://127.0.0.1:9/v1\n"
        "    models:\n"
        "      model:\n"
        "        name: 显示名\n",
    )
    app = build_app(config)
    async with app.run_test() as pilot:
        assert "显示名" in pilot.app.query_one(StatusBar).text


def test_build_app_requires_model(tmp_path: Path) -> None:
    config = _write_config(tmp_path, "workspace:\n  dir: .\n")
    with pytest.raises(ConfigError, match="default_model"):
        build_app(config)


def test_build_app_validates_default_model_key_at_startup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = _write_config(
        tmp_path,
        "default_model: openai/gpt\nproviders:\n  openai:\n    type: openai\n    models:\n      gpt: {}\n",
    )
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_app(config)


async def test_async_runner_factory_is_awaited_on_mount() -> None:
    """异步 runner 装配（MCP connect 等）在 on_mount 完成，提交前 runner 已就绪。"""

    async def factory(sink):  # noqa: ANN001, ANN202 - 测试内联协议实现
        return ScriptedRunner(sink)

    app = IntelliAgentApp(runner_factory=factory, model="fake/model", cwd=Path("/work"))
    async with app.run_test():
        assert isinstance(app.task_runner, ScriptedRunner)


async def test_async_startup_failure_exits_with_startup_code(
    capfd: pytest.CaptureFixture[str],
) -> None:
    """MCP 连接等异步启动失败：写脱敏错误并以启动失败码退出。"""

    async def factory(sink):  # noqa: ANN001, ANN202 - 测试内联协议实现
        raise RuntimeError("mcp connect failed")

    app = IntelliAgentApp(runner_factory=factory, model="fake/model", cwd=Path("/work"))
    async with app.run_test():
        pass
    assert app.return_code == 2
    assert "mcp connect failed" in capfd.readouterr().err


async def test_app_invokes_close_callback_on_exit() -> None:
    """应用退出时释放运行时资源（storage 连接）。"""
    closed: list[bool] = []

    async def close() -> None:
        closed.append(True)

    app = IntelliAgentApp(
        runner_factory=ScriptedRunner,
        model="fake/model",
        cwd=Path("/work"),
        on_close=close,
    )
    async with app.run_test():
        pass
    assert closed == [True]

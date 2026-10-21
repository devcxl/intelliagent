"""最小组装：intelliagent.yaml → 引擎 + TUI（issue #60 无头模式组装未合并前的过渡实现）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config.yaml_config import ConfigError
from src.core.engine import Engine
from src.tui.assembly import build_app
from src.tui.widgets import StatusBar


def _write_config(tmp_path: Path, body: str) -> Path:
    config = tmp_path / "intelliagent.yaml"
    config.write_text(body, encoding="utf-8")
    return config


def test_build_app_wires_engine_as_task_runner(tmp_path: Path) -> None:
    config = _write_config(tmp_path, "model: fake/model\nworkspace:\n  dir: /work/project\n")
    app = build_app(config)
    assert isinstance(app.task_runner, Engine)


async def test_status_bar_shows_configured_cwd_and_model(tmp_path: Path) -> None:
    config = _write_config(tmp_path, "model: fake/model\nworkspace:\n  dir: /work/project\n")
    app = build_app(config)
    async with app.run_test() as pilot:
        bar = pilot.app.query_one(StatusBar)
        assert "/work/project" in bar.text
        assert "fake/model" in bar.text


def test_build_app_requires_model(tmp_path: Path) -> None:
    config = _write_config(tmp_path, "workspace:\n  dir: .\n")
    with pytest.raises(ConfigError, match="model"):
        build_app(config)

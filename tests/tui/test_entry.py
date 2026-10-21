"""TUI 入口（README：uv run python -m src.tui）：装配接线与启动失败路径。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tui.__main__ import EXIT_STARTUP_FAILURE, main


class _RecordingApp:
    """替换真实 TUI：只记录 run 是否被调用，避免测试拉起终端。"""

    def __init__(self) -> None:
        self.ran = False

    def run(self) -> None:
        self.ran = True


def test_main_builds_and_runs_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _RecordingApp()
    monkeypatch.setattr("src.tui.__main__.build_app", lambda: app)
    assert main() == 0
    assert app.ran


def test_main_reports_missing_config_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """缺 intelliagent.yaml：给可诊断的脱敏错误与退出码 2，而不是 traceback。"""
    monkeypatch.chdir(tmp_path)
    assert main() == EXIT_STARTUP_FAILURE
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "intelliagent.yaml" in err

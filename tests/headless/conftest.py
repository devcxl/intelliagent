"""headless 测试隔离：默认 skill 用户路径不读取真实 HOME。"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把 HOME 指向测试临时目录，避免开发者本机 skill 影响请求内容。"""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

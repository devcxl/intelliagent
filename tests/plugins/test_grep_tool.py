"""grep 行为测试：匹配数 / 行宽 / 总量限额，ripgrep 缺失与失败可诊断。

规格来源：docs/pi-engine-principles.md §5「工具结果大小控制」。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from src.plugins.basic_tools.grep_tool import grep_tool
from src.utils.path_policy import PathPolicy

requires_rg = pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep 未安装")


def envelope(result: str) -> dict[str, Any]:
    data = json.loads(result)
    assert isinstance(data, dict)
    return data


@pytest.fixture
def policy(tmp_path: Path) -> PathPolicy:
    return PathPolicy(workspace=tmp_path)


class TestGrepTool:
    @requires_rg
    async def test_reports_matches_with_line_numbers(self, tmp_path: Path, policy: PathPolicy) -> None:
        (tmp_path / "a.txt").write_text("no\nneedle here\nstill needle\n", encoding="utf-8")

        data = envelope(await grep_tool(path_policy=policy).run(pattern="needle", path=str(tmp_path)))

        assert data["status"] == "ok"
        assert data["match_count"] == 2
        assert data["truncated"] is False
        matches = sorted(data["matches"], key=lambda m: m["line_number"])
        assert matches[0]["line_number"] == 2
        assert matches[0]["line"] == "needle here"
        assert matches[1]["line_number"] == 3

    @requires_rg
    async def test_no_matches_is_success(self, tmp_path: Path, policy: PathPolicy) -> None:
        (tmp_path / "a.txt").write_text("nothing\n", encoding="utf-8")

        data = envelope(await grep_tool(path_policy=policy).run(pattern="absent", path=str(tmp_path)))

        assert data["status"] == "ok"
        assert data["match_count"] == 0
        assert data["matches"] == []

    @requires_rg
    async def test_match_count_limit(self, tmp_path: Path, policy: PathPolicy) -> None:
        (tmp_path / "many.txt").write_text("".join(f"needle {i}\n" for i in range(150)), encoding="utf-8")

        data = envelope(await grep_tool(path_policy=policy).run(pattern="needle", path=str(tmp_path / "many.txt")))

        assert data["status"] == "ok"
        assert data["match_count"] == 100
        assert data["truncated"] is True

    @requires_rg
    async def test_line_width_limit(self, tmp_path: Path, policy: PathPolicy) -> None:
        (tmp_path / "wide.txt").write_text("needle " + "a" * 1000 + "\n", encoding="utf-8")

        data = envelope(await grep_tool(path_policy=policy).run(pattern="needle", path=str(tmp_path / "wide.txt")))

        assert data["status"] == "ok"
        assert data["match_count"] == 1
        assert len(data["matches"][0]["line"]) == 500

    @requires_rg
    async def test_total_output_limit(self, tmp_path: Path, policy: PathPolicy) -> None:
        (tmp_path / "long.txt").write_text("".join("needle " + "a" * 493 + "\n" for _ in range(150)), encoding="utf-8")

        data = envelope(await grep_tool(path_policy=policy).run(pattern="needle", path=str(tmp_path / "long.txt")))

        assert data["status"] == "ok"
        assert data["truncated"] is True
        assert data["match_count"] < 150
        assert sum(len(m["line"]) for m in data["matches"]) <= 50_000

    @requires_rg
    async def test_invalid_regex_is_diagnosable(self, tmp_path: Path, policy: PathPolicy) -> None:
        (tmp_path / "a.txt").write_text("text\n", encoding="utf-8")

        data = envelope(await grep_tool(path_policy=policy).run(pattern="([unclosed", path=str(tmp_path)))

        assert data["status"] == "error"
        assert data["code"] == "GREP_FAILED"
        assert "regex" in data["detail"]

    async def test_missing_ripgrep_is_diagnosable(
        self, tmp_path: Path, policy: PathPolicy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.plugins.basic_tools.grep_tool.shutil.which", lambda name: None)
        (tmp_path / "a.txt").write_text("text\n", encoding="utf-8")

        data = envelope(await grep_tool(path_policy=policy).run(pattern="text", path=str(tmp_path)))

        assert data["status"] == "error"
        assert data["code"] == "RIPGREP_NOT_FOUND"
        assert "ripgrep" in data["error"]

    async def test_path_outside_workspace_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await grep_tool(path_policy=policy).run(pattern="x", path=str(tmp_path.parent)))

        assert data["status"] == "error"
        assert data["code"] == "PATH_OUTSIDE_WORKSPACE"

    async def test_missing_target_is_diagnosable(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await grep_tool(path_policy=policy).run(pattern="x", path=str(tmp_path / "ghost")))

        assert data["status"] == "error"
        assert data["code"] == "FILE_NOT_FOUND"

    async def test_empty_pattern_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await grep_tool(path_policy=policy).run(pattern="", path=str(tmp_path)))

        assert data["status"] == "error"
        assert data["code"] == "EMPTY_PATTERN"

"""read/write/edit 行为测试：pi 输出纪律（分页续读 / 不回灌文件 / 精确匹配只回 diff）。

规格来源：docs/pi-engine-principles.md §5「工具结果大小控制」。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.plugins.basic_tools.file_tools import edit_tool, read_tool, write_tool
from src.utils.path_policy import PathPolicy


def envelope(result: str) -> dict[str, Any]:
    data = json.loads(result)
    assert isinstance(data, dict)
    return data


@pytest.fixture
def policy(tmp_path: Path) -> PathPolicy:
    return PathPolicy(workspace=tmp_path)


class TestReadTool:
    async def test_returns_window_with_continuation_note(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "sample.txt"
        target.write_text("".join(f"line{i}\n" for i in range(1, 11)), encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target), offset=1, limit=4))

        assert data["status"] == "ok"
        assert data["content"] == "line1\nline2\nline3\nline4"
        assert data["start_line"] == 1
        assert data["end_line"] == 4
        assert data["total_lines"] == 10
        assert data["truncated"] is True
        assert data["note"] == "[Showing lines 1-4 of 10. Use offset=5 to continue.]"

    async def test_offset_pages_through_file(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "sample.txt"
        target.write_text("".join(f"line{i}\n" for i in range(1, 11)), encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target), offset=5, limit=4))

        assert data["content"] == "line5\nline6\nline7\nline8"
        assert data["start_line"] == 5
        assert data["end_line"] == 8
        assert data["note"] == "[Showing lines 5-8 of 10. Use offset=9 to continue.]"

    async def test_last_page_has_no_continuation_note(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "sample.txt"
        target.write_text("".join(f"line{i}\n" for i in range(1, 11)), encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target), offset=9, limit=4))

        assert data["content"] == "line9\nline10"
        assert data["end_line"] == 10
        assert data["truncated"] is False
        assert data["note"] == ""

    async def test_limit_is_clamped_to_2000_lines(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "big.txt"
        target.write_text("".join(f"line{i}\n" for i in range(1, 2101)), encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target), limit=5000))

        assert data["end_line"] == 2000
        assert data["total_lines"] == 2100
        assert data["note"] == "[Showing lines 1-2000 of 2100. Use offset=2001 to continue.]"

    async def test_char_budget_stops_window_early(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "wide.txt"
        target.write_text("".join("x" * 20_000 + "\n" for _ in range(5)), encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target), offset=1, limit=5))

        assert data["end_line"] == 2
        assert data["total_lines"] == 5
        assert data["truncated"] is True
        assert data["note"] == "[Showing lines 1-2 of 5. Use offset=3 to continue.]"

    async def test_single_huge_line_is_truncated_with_note(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "oneline.txt"
        target.write_text("y" * 60_000 + "\n", encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target)))

        assert len(data["content"]) == 50_000
        assert data["end_line"] == 1
        assert data["truncated"] is True
        assert "truncated" in data["note"]

    async def test_offset_beyond_eof_is_diagnosable(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "sample.txt"
        target.write_text("line1\n", encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target), offset=99))

        assert data["status"] == "error"
        assert data["code"] == "OFFSET_OUT_OF_RANGE"
        assert data["total_lines"] == 1

    async def test_empty_file_returns_empty_content(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "empty.txt"
        target.write_text("", encoding="utf-8")

        data = envelope(await read_tool(path_policy=policy).run(path=str(target)))

        assert data["status"] == "ok"
        assert data["content"] == ""
        assert data["total_lines"] == 0

    async def test_missing_file_is_diagnosable(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await read_tool(path_policy=policy).run(path=str(tmp_path / "ghost.txt")))

        assert data["status"] == "error"
        assert data["code"] == "FILE_NOT_FOUND"

    async def test_directory_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await read_tool(path_policy=policy).run(path=str(tmp_path)))

        assert data["status"] == "error"
        assert data["code"] == "IS_DIRECTORY"

    async def test_path_outside_workspace_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await read_tool(path_policy=policy).run(path=str(tmp_path.parent / "escape.txt")))

        assert data["status"] == "error"
        assert data["code"] == "PATH_OUTSIDE_WORKSPACE"

    async def test_workspace_root_env_var_is_respected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INTELLIAGENT_WORKSPACE_ROOT", str(tmp_path))
        target = tmp_path / "in.txt"
        target.write_text("ok\n", encoding="utf-8")

        data = envelope(await read_tool().run(path=str(target)))
        assert data["status"] == "ok"

        escape = envelope(await read_tool().run(path=str(tmp_path.parent / "escape.txt")))
        assert escape["code"] == "PATH_OUTSIDE_WORKSPACE"


class TestWriteTool:
    async def test_writes_file_without_echoing_content(self, tmp_path: Path, policy: PathPolicy) -> None:
        body = "secret-body\n" * 10
        target = tmp_path / "sub" / "new.txt"

        data = envelope(await write_tool(path_policy=policy).run(path=str(target), content=body))

        assert data["status"] == "ok"
        assert target.read_text(encoding="utf-8") == body
        assert "content" not in data
        assert "secret-body" not in json.dumps(data, ensure_ascii=False)
        assert data["chars"] == len(body)

    async def test_overwrites_existing_file(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "file.txt"
        target.write_text("old\n", encoding="utf-8")

        data = envelope(await write_tool(path_policy=policy).run(path=str(target), content="new\n"))

        assert data["status"] == "ok"
        assert target.read_text(encoding="utf-8") == "new\n"

    async def test_oversized_content_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await write_tool(path_policy=policy).run(path=str(tmp_path / "big.txt"), content="x" * 1_000_001))

        assert data["status"] == "error"
        assert data["code"] == "CONTENT_TOO_LARGE"

    async def test_non_string_content_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await write_tool(path_policy=policy).run(path=str(tmp_path / "x.txt"), content=123))

        assert data["status"] == "error"
        assert data["code"] == "INVALID_ARGUMENT"

    async def test_path_outside_workspace_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(await write_tool(path_policy=policy).run(path=str(tmp_path.parent / "escape.txt"), content="x"))

        assert data["status"] == "error"
        assert data["code"] == "PATH_OUTSIDE_WORKSPACE"


class TestEditTool:
    async def test_exact_match_is_whitespace_sensitive(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "code.py"
        target.write_text("x\n  indented  \ny\n", encoding="utf-8")

        data = envelope(
            await edit_tool(path_policy=policy).run(
                path=str(target), oldString="  indented  ", newString="PLAIN", replaceAll=False
            )
        )

        assert data["status"] == "ok"
        assert target.read_text(encoding="utf-8") == "x\nPLAIN\ny\n"
        assert data["replacements"] == 1

    async def test_multiline_match_preserves_leading_newlines(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "code.py"
        original = "def f():\n    return 1\n\n\ndef g():\n    return 2\n"
        target.write_text(original, encoding="utf-8")

        data = envelope(
            await edit_tool(path_policy=policy).run(
                path=str(target), oldString="\n\n\ndef g():", newString="\n\ndef g():", replaceAll=False
            )
        )

        assert data["status"] == "ok"
        assert target.read_text(encoding="utf-8") == "def f():\n    return 1\n\n\ndef g():\n    return 2\n"

    async def test_multiple_matches_require_explicit_strategy(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "dup.txt"
        original = "foo bar foo\n"
        target.write_text(original, encoding="utf-8")

        data = envelope(
            await edit_tool(path_policy=policy).run(path=str(target), oldString="foo", newString="baz", replaceAll=False)
        )

        assert data["status"] == "error"
        assert data["code"] == "MULTIPLE_MATCHES"
        assert data["matches"] == 2
        assert target.read_text(encoding="utf-8") == original

    async def test_replace_all_replaces_every_match(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "dup.txt"
        target.write_text("foo bar foo\n", encoding="utf-8")

        data = envelope(
            await edit_tool(path_policy=policy).run(path=str(target), oldString="foo", newString="baz", replaceAll=True)
        )

        assert data["status"] == "ok"
        assert data["replacements"] == 2
        assert target.read_text(encoding="utf-8") == "baz bar baz\n"

    async def test_returns_diff_without_full_file_content(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "big.txt"
        target.write_text("marker\n" + "".join(f"body-{i:02d}\n" for i in range(50)), encoding="utf-8")

        data = envelope(
            await edit_tool(path_policy=policy).run(path=str(target), oldString="marker", newString="marker2")
        )

        assert data["status"] == "ok"
        assert "@@" in data["diff"]
        assert "-marker\n" in data["diff"]
        assert "+marker2\n" in data["diff"]
        assert "body-049" not in data["diff"]

    async def test_huge_diff_is_capped(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "oneline.txt"
        target.write_text("A" + "z" * 60_000 + "\n", encoding="utf-8")

        data = envelope(await edit_tool(path_policy=policy).run(path=str(target), oldString="A", newString="B"))

        assert data["status"] == "ok"
        assert len(data["diff"]) <= 51_000
        assert data["truncated"] is True

    async def test_missing_old_string_is_diagnosable(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "file.txt"
        target.write_text("hello\n", encoding="utf-8")

        data = envelope(await edit_tool(path_policy=policy).run(path=str(target), oldString="absent", newString="x"))

        assert data["status"] == "error"
        assert data["code"] == "OLD_STRING_NOT_FOUND"

    async def test_empty_old_string_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "file.txt"
        target.write_text("hello\n", encoding="utf-8")

        data = envelope(await edit_tool(path_policy=policy).run(path=str(target), oldString="", newString="x"))

        assert data["status"] == "error"
        assert data["code"] == "EMPTY_OLD_STRING"

    async def test_identical_strings_are_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        target = tmp_path / "file.txt"
        target.write_text("hello\n", encoding="utf-8")

        data = envelope(await edit_tool(path_policy=policy).run(path=str(target), oldString="hello", newString="hello"))

        assert data["status"] == "error"
        assert data["code"] == "IDENTICAL_STRINGS"

    async def test_path_outside_workspace_is_rejected(self, tmp_path: Path, policy: PathPolicy) -> None:
        data = envelope(
            await edit_tool(path_policy=policy).run(
                path=str(tmp_path.parent / "escape.txt"), oldString="a", newString="b"
            )
        )

        assert data["status"] == "error"
        assert data["code"] == "PATH_OUTSIDE_WORKSPACE"

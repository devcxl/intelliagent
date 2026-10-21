"""bash 行为测试：尾窗保留 + 全量落盘、超时杀进程组、非零退出码不伪装成功。

规格来源：docs/pi-engine-principles.md §5「工具结果大小控制」。
"""

from __future__ import annotations

import asyncio
import json
import shlex
import time
from pathlib import Path
from typing import Any

from src.plugins.basic_tools.bash_tool import bash_tool
from src.plugins.basic_tools.offload import OutputAccumulator


def envelope(result: str) -> dict[str, Any]:
    data = json.loads(result)
    assert isinstance(data, dict)
    return data


class TestBashTool:
    async def test_success_returns_output(self) -> None:
        data = envelope(await bash_tool().run(command="echo hello"))

        assert data["status"] == "ok"
        assert data["returncode"] == 0
        assert "hello" in data["output"]
        assert data["truncated"] is False

    async def test_nonzero_exit_is_not_disguised_as_success(self) -> None:
        data = envelope(await bash_tool().run(command="echo out; echo err >&2; exit 3"))

        assert data["status"] == "error"
        assert data["code"] == "COMMAND_FAILED"
        assert data["returncode"] == 3
        assert "out" in data["output"]
        assert "err" in data["output"]

    async def test_output_offload_keeps_tail_and_full_file(self) -> None:
        data = envelope(await bash_tool().run(command="seq 1 20000"))

        assert data["status"] == "ok"
        assert data["truncated"] is True
        tail_lines = data["output"].splitlines()
        assert tail_lines[0] == "18001"
        assert tail_lines[-1] == "20000"
        assert len(tail_lines) == 2000

        full_output = Path(data["full_output_file"]).read_text(encoding="utf-8")
        assert full_output.startswith("1\n")
        assert full_output.endswith("20000\n")

    async def test_timeout_kills_whole_process_group(self, tmp_path: Path) -> None:
        marker = tmp_path / "alive.txt"
        inner = f"sleep 2; echo alive > {shlex.quote(str(marker))}"
        command = f"sh -c {shlex.quote(inner)} & wait"

        data = envelope(await bash_tool().run(command=command, timeout=0.5))

        assert data["status"] == "error"
        assert data["code"] == "TIMEOUT"
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            assert not marker.exists(), "进程组未被整体终止：孙进程仍写出了标记文件"
            await asyncio.sleep(0.1)

    async def test_empty_command_is_rejected(self) -> None:
        data = envelope(await bash_tool().run(command="   "))

        assert data["status"] == "error"
        assert data["code"] == "EMPTY_COMMAND"

    async def test_invalid_timeout_is_rejected(self) -> None:
        data = envelope(await bash_tool().run(command="echo ok", timeout=0))

        assert data["status"] == "error"
        assert data["code"] == "INVALID_ARGUMENT"


class TestOutputAccumulator:
    def test_tail_keeps_last_lines_within_char_budget(self) -> None:
        acc = OutputAccumulator(max_lines=3, max_chars=25, offload_prefix="test-acc")
        acc.feed("a\nb\nc\nd\ne\n".encode("utf-8"))
        acc.close()

        assert acc.tail == "c\nd\ne\n"
        assert acc.truncated is True
        full = Path(acc.full_output_path or "").read_text(encoding="utf-8")
        assert full == "a\nb\nc\nd\ne\n"

    def test_tail_keeps_last_chars_for_long_lines(self) -> None:
        acc = OutputAccumulator(max_lines=100, max_chars=10, offload_prefix="test-acc")
        acc.feed(("x" * 30).encode("utf-8"))
        acc.close()

        assert acc.tail == "x" * 10
        assert acc.truncated is True

    def test_streaming_decode_handles_split_multibyte_characters(self) -> None:
        acc = OutputAccumulator(max_lines=10, max_chars=100, offload_prefix="test-acc")
        encoded = "中文ok\n".encode("utf-8")
        acc.feed(encoded[:1])
        acc.feed(encoded[1:3])
        acc.feed(encoded[3:])
        acc.close()

        assert acc.tail == "中文ok\n"

    def test_small_output_is_not_offloaded(self) -> None:
        acc = OutputAccumulator(max_lines=10, max_chars=100, offload_prefix="test-acc")
        acc.feed(b"tiny\n")
        acc.close()

        assert acc.tail == "tiny\n"
        assert acc.truncated is False
        assert acc.full_output_path is None

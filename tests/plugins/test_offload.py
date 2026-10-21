"""OutputAccumulator / LineSplitter 测试（PR #69 审查回归：清理、有界、尾部 flush）。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from src.plugins.basic_tools.offload import MAX_LINE_CHARS, LineSplitter, OutputAccumulator


class TestReviewRegressions:
    """PR #69 审查回归：临时文件清理、LineSplitter 有界、尾部 flush 落盘。"""

    def test_stale_offload_files_are_cleaned(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        stale = tmp_path / "intelliagent-bash-old.log"
        stale.write_text("old", encoding="utf-8")
        old = time.time() - 48 * 3600
        os.utime(stale, (old, old))

        acc = OutputAccumulator(max_lines=2, max_chars=10, offload_prefix="intelliagent-bash")
        acc.feed(b"x" * 100)
        acc.close()
        assert not stale.exists()  # 超龄文件被清理
        assert acc.full_output_path is not None  # 当前落盘文件保留供回读

    def test_line_splitter_caps_unbounded_line(self) -> None:
        splitter = LineSplitter()
        lines = splitter.feed(b"a" * 200_000)
        assert lines, "超长无换行内容应截断吐出而非无界堆积"
        assert all(len(line) <= MAX_LINE_CHARS + 32 for line in lines)

    def test_close_flushes_remainder_to_offload(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        acc = OutputAccumulator(max_lines=1, max_chars=5, offload_prefix="intelliagent-bash")
        acc.feed(b"a" * 100)  # 触发落盘
        acc.feed(b"\xe4\xb8")  # 半个多字节字符留在解码器
        acc.close()
        assert acc.full_output_path is not None
        offloaded = Path(acc.full_output_path).read_text(encoding="utf-8")
        assert len(offloaded) == acc.total_chars  # 尾部 flush 进落盘，落盘即完整输出

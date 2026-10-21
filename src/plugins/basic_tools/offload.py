"""流式输出累积：增量 UTF-8 解码、滚动尾窗限内存、超限自动全量落盘（pi 的 OutputAccumulator 语义）。"""

from __future__ import annotations

import codecs
import os
import tempfile
from pathlib import Path
from typing import TextIO


class OutputAccumulator:
    """消费命令输出字节流：保留尾部窗口（行数与字符双限），超限时把完整输出落盘临时文件。"""

    def __init__(self, *, max_lines: int, max_chars: int, offload_prefix: str) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._max_lines = max_lines
        self._max_chars = max_chars
        self._offload_prefix = offload_prefix
        self._tail = ""
        self._accumulated = ""
        self._total_chars = 0
        self._total_lines = 0
        self._offload_file: TextIO | None = None
        self._offload_path: Path | None = None

    def feed(self, chunk: bytes) -> None:
        """消费一段输出字节（可从多字节字符中间切开）。"""
        text = self._decoder.decode(chunk)
        if not text:
            return
        self._total_chars += len(text)
        self._total_lines += text.count("\n")
        if self._offload_file is None and self._exceeds_window():
            self._open_offload()
        if self._offload_file is not None:
            self._offload_file.write(text)
        else:
            self._accumulated += text
        self._tail = (self._tail + text)[-self._max_chars :]

    def close(self) -> None:
        """冲刷解码器与落盘文件；此后可读取 tail / full_output_path。"""
        remainder = self._decoder.decode(b"", final=True)
        if remainder:
            self._total_chars += len(remainder)
            self._tail = (self._tail + remainder)[-self._max_chars :]
        if self._offload_file is not None:
            self._offload_file.close()
            self._offload_file = None

    @property
    def tail(self) -> str:
        """尾窗：最后 max_lines 行且不超过 max_chars 字符。"""
        lines = self._tail.splitlines(keepends=True)
        return "".join(lines[-self._max_lines :])

    @property
    def truncated(self) -> bool:
        """输出是否超出尾窗（完整输出已落盘）。"""
        return self._offload_path is not None

    @property
    def full_output_path(self) -> str | None:
        """完整输出的落盘路径；未落盘时为 None。"""
        return str(self._offload_path) if self._offload_path is not None else None

    @property
    def total_chars(self) -> int:
        """累计输出字符数。"""
        return self._total_chars

    def _exceeds_window(self) -> bool:
        return self._total_chars > self._max_chars or self._total_lines > self._max_lines

    def _open_offload(self) -> None:
        fd, name = tempfile.mkstemp(prefix=self._offload_prefix, suffix=".log")
        self._offload_path = Path(name)
        self._offload_file = os.fdopen(fd, "w", encoding="utf-8")
        if self._accumulated:
            self._offload_file.write(self._accumulated)
            self._accumulated = ""


class LineSplitter:
    """把字节流切成行（跨块增量 UTF-8 解码），供 grep 解析 ripgrep 输出。"""

    def __init__(self) -> None:
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._buffer = ""

    def feed(self, chunk: bytes) -> list[str]:
        """消费一段字节，返回其中已完整的行（不含换行符）。"""
        self._buffer += self._decoder.decode(chunk)
        parts = self._buffer.split("\n")
        self._buffer = parts.pop()
        return [part[:-1] if part.endswith("\r") else part for part in parts]

    def close(self) -> list[str]:
        """返回最后一条未以换行结尾的行（若有）。"""
        rest = self._buffer + self._decoder.decode(b"", final=True)
        self._buffer = ""
        return [rest] if rest else []

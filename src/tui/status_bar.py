"""底部状态栏：运行状态与耗时、模型、本轮 token、工作目录（issue #90）。"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from textual.timer import Timer
from textual.widgets import Static

from src.llm.stream import Usage

TOKEN_SEGMENT_PREFIX = "本轮 tok"


class StatusBar(Static):
    """底部状态栏：运行状态与耗时、模型、本轮 token、工作目录（issue #90）。

    计时由 AgentStart/AgentEnd 驱动：运行中每秒刷新，收束后保留最终耗时，下一次 run
    重新计时。本轮 token 在 run 内按 MessageEnd.usage 累计，新 run 清空（上下文占用
    百分比不在本 ticket 范围）。clock 可注入，计时测试无需真实等待。
    """

    def __init__(self, cwd: Path, model: str, *, clock: Callable[[], float] | None = None) -> None:
        super().__init__("", id="status-bar", markup=False)
        self._cwd = cwd
        self._model = model
        self._clock = clock or time.monotonic
        self._run_state = "就绪"
        self._started_at: float | None = None
        self._finished_elapsed: float | None = None
        self._usage: Usage | None = None
        self._timer: Timer | None = None
        self._refresh()

    def start_run(self) -> None:
        """一次 run 开始：清零计时与 token，开始每秒刷新。"""
        self._stop_timer()
        self._run_state = "运行中"
        self._started_at = self._clock()
        self._finished_elapsed = None
        self._usage = None
        self._timer = self.set_interval(1.0, self._tick)
        self._refresh()

    def finish_run(self, state: str) -> None:
        """一次 run 收束：冻结最终耗时并停止刷新，状态文案取收束方式。"""
        if self._started_at is not None:
            self._finished_elapsed = self.elapsed_seconds
        self._started_at = None
        self._stop_timer()
        self._run_state = state
        self._refresh()

    def set_run_state(self, state: str) -> None:
        """更新运行状态（就绪/运行中/中止中/已完成/已终止/出错/已中止）。"""
        self._run_state = state
        self._refresh()

    def record_usage(self, usage: Usage) -> None:
        """累计本轮 token 用量（provider 真实值）；无 usage 的收束不会被伪造为 0。"""
        if self._usage is None:
            self._usage = usage
        else:
            self._usage = Usage(
                prompt_tokens=self._usage.prompt_tokens + usage.prompt_tokens,
                completion_tokens=self._usage.completion_tokens + usage.completion_tokens,
                total_tokens=self._usage.total_tokens + usage.total_tokens,
            )
        self._refresh()

    @property
    def text(self) -> str:
        """状态栏纯文本，供测试与诊断读取。"""
        return self._render_text()

    @property
    def elapsed_seconds(self) -> float:
        """当前 run 已用秒数：运行中随时钟推进，收束后为冻结的最终值。"""
        if self._started_at is None:
            return self._finished_elapsed or 0.0
        return max(0.0, self._clock() - self._started_at)

    def _tick(self) -> None:
        """每秒刷新：无运行中的计时则停表，避免空转。"""
        if self._started_at is None:
            self._stop_timer()
            return
        self._refresh()

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _refresh(self) -> None:
        self.update(self._render_text())

    def _render_text(self) -> str:
        parts = [self._state_text(), f"模型 {self._model}"]
        if self._usage is not None:
            parts.append(
                f"{TOKEN_SEGMENT_PREFIX} ↑{_format_token_count(self._usage.prompt_tokens)} "
                f"↓{_format_token_count(self._usage.completion_tokens)}"
            )
        parts.append(f"目录 {self._display_cwd()}")
        return "  ".join(parts)

    def _state_text(self) -> str:
        if self._started_at is not None or self._finished_elapsed is not None:
            return f"{self._run_state} {int(self.elapsed_seconds)}s"
        return self._run_state

    def _display_cwd(self) -> str:
        """工作目录：home 前缀缩略为 ~，窄终端下把空间留给运行信息。"""
        home = Path.home().resolve()
        try:
            relative = self._cwd.resolve().relative_to(home)
        except ValueError:
            return str(self._cwd)
        return "~" if str(relative) == "." else f"~/{relative}"


def _format_token_count(value: int) -> str:
    """token 数：千级以上用 k 缩写（1.2k），千级以下保留原值。"""
    if value < 1000:
        return str(value)
    return f"{value / 1000:.1f}k"

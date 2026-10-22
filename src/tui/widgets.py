"""TUI 组件：消息流、消息单元、工具调用折叠面板、状态栏（ADR 0009 的 pi 最简形态）。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.containers import VerticalScroll
from textual.timer import Timer
from textual.widgets import Collapsible, Static

from src.core.agent_events import MessageDelta
from src.core.tool_pipeline import Observation
from src.llm.stream import Error, TextDelta, Usage

ROLE_LABELS = {"user": "你", "assistant": "助手", "system": "系统"}
TOOL_STATE_LABELS = {"running": "执行中", "success": "成功", "denied": "已拒绝", "error": "失败"}
EMPTY_MESSAGE_PLACEHOLDER = "（无内容）"
TOOL_BODY_MAX_LINES = 20
"""工具面板展开正文的最高行数：超出后在面板内滚动，不挤占消息流。"""

TOKEN_SEGMENT_PREFIX = "tok"


class MessageView(Static):
    """一条 Message 的渲染单元（CONTEXT 术语：Message）。

    流式增量渲染（issue #63）：append_delta 收增量即安排重绘，同一轮到达的增量合并成一次
    update（pi 的 requestRender 合并语义），且只重绘本单元、不触碰消息流其余部分。
    flush 是强制收口点（finish 与半程清算共用）；收束时空消息落空态占位。
    """

    def __init__(self, role: str, *, text: str = "", message_id: str | None = None) -> None:
        self.role = role
        self.message_id = message_id
        self._text_parts: list[str] = [text] if text else []
        self._received_delta = bool(text)
        self._finished = False
        self._dirty = False
        self._flush_scheduled = False
        self._rendered_text = self._display_text()
        super().__init__(self._renderable(), classes=f"message role-{role}")

    @property
    def text(self) -> str:
        """消息正文（不含角色标签）：已收到的全部增量拼接，供测试与诊断读取。"""
        return "".join(self._text_parts)

    @property
    def rendered_text(self) -> str:
        """已落屏的展示正文（含空态占位）：随 flush 推进，供测试与诊断读取。"""
        return self._rendered_text

    def append_delta(self, delta: MessageDelta) -> None:
        """收一个流式增量：进缓冲并安排合并重绘，不逐 delta 全量重绘（issue #63）。"""
        self._received_delta = True
        if isinstance(delta, TextDelta):
            self._text_parts.append(delta.text)
        elif isinstance(delta, Error):
            self._text_parts.append(f"\n（流式错误：{delta.message}）")
        # ToolCallDelta 不进消息正文：工具调用由 tool_execution_* 事件渲染成折叠面板
        self._dirty = True
        if not self._flush_scheduled:
            self._flush_scheduled = True
            if not self.call_later(self._flush_soon):
                self._flush_soon()

    def flush(self) -> None:
        """把缓冲的增量立即落屏（幂等；无待落屏内容时不动，避免多余重绘）。

        顺带复位合并标志：call_later 回调被丢弃（pump 关闭竞态）时不留悬挂，
        后续增量仍能安排重绘。
        """
        self._flush_scheduled = False
        if not self._dirty:
            return
        self._dirty = False
        self._redraw()

    def finish(self) -> None:
        """消息收束：空态占位生效并落屏。"""
        self._finished = True
        self._dirty = True
        self.flush()

    def settle(self) -> None:
        """收束清算（缺 MessageEnd 的兜底）：缓冲落屏，空消息落空态占位而非裸角色标签。"""
        self.finish()

    def _flush_soon(self) -> None:
        """合并窗口收口（call_later 回调）：一轮事件的增量在此合成一次重绘。"""
        self._flush_scheduled = False
        self.flush()

    def _redraw(self) -> None:
        self._rendered_text = self._display_text()
        self.update(self._renderable())

    def _display_text(self) -> str:
        text = self.text
        if text or not self._finished or self._received_delta:
            return text
        return EMPTY_MESSAGE_PLACEHOLDER

    def _renderable(self) -> Text:
        label = ROLE_LABELS.get(self.role, self.role)
        return Text.assemble((f"{label}  ", "bold"), self._rendered_text)


class ToolCallPanel(Collapsible):
    """一次工具调用的折叠面板：执行中自动展开，结束后自动折叠为一行摘要。

    标题由工具名、状态与耗时组成；展开正文限制最高 20 行并在面板内滚动，
    超长输出不把消息流顶走（issue #90）。
    """

    def __init__(self, tool_call_id: str, name: str, arguments: str | Mapping[str, Any]) -> None:
        self.tool_call_id = tool_call_id
        self.tool_name = name
        self._arguments = arguments
        self._status = "running"
        self._result_text = ""
        self._duration_ms = 0.0
        self._progress_parts: list[str] = []
        self._body_text = Static("", classes="tool-body-text")
        self._body = VerticalScroll(self._body_text, classes="tool-body")
        self._body_text.update(self._render_body())
        super().__init__(self._body, title=self._render_title(), collapsed=False)

    @property
    def body_text(self) -> str:
        """面板正文纯文本（参数、进度、结果），供测试与诊断读取。"""
        sections = [f"参数:\n{_format_arguments(self._arguments)}"]
        if self._progress_parts:
            sections.append(f"进度:\n{''.join(self._progress_parts)}")
        if self._status != "running":
            sections.append(f"结果:\n{self._result_text}")
        return "\n".join(sections)

    def append_progress(self, delta: str) -> None:
        """记录工具执行中的进度增量（流式工具接入后按增量追加显示）。"""
        self._progress_parts.append(delta)
        self._body_text.update(self._render_body())

    def finish(self, observation: Observation) -> None:
        """写最终结果：状态、耗时与结果文本落定，面板自动收成一行摘要。"""
        self._status = observation.status
        self._result_text = _result_text(observation)
        self._duration_ms = observation.duration_ms
        self.title = self._render_title()
        self._body_text.update(self._render_body())
        self.collapsed = True

    def _render_title(self) -> str:
        state = TOOL_STATE_LABELS.get(self._status, self._status)
        if self._status == "running":
            return f"{self.tool_name} · {state}"
        return f"{self.tool_name} · {state} · {_format_duration(self._duration_ms)}"

    def _render_body(self) -> Text:
        return Text(self.body_text)


class MessageStream(VerticalScroll):
    """消息流区域：按事件到达顺序追加消息单元与工具调用面板（pi 的内联工具调用）。"""

    def add_message(self, view: MessageView) -> None:
        """追加一个消息单元到流末尾。"""
        self.mount(view)
        self.scroll_end(animate=False)

    def add_tool_panel(self, panel: ToolCallPanel) -> None:
        """追加一个工具调用折叠面板到流末尾。"""
        self.mount(panel)
        self.scroll_end(animate=False)

    def flush_pending(self) -> None:
        """半程清算：缺 MessageEnd 的消息按收束落屏——缓冲增量落屏，空消息落空态占位
        （而非裸角色标签，PR #78 审查 Standards medium）。已 finish 的单元幂等跳过。"""
        for view in self.query(MessageView):
            view.settle()


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


def _format_arguments(arguments: str | Mapping[str, Any]) -> str:
    if isinstance(arguments, Mapping):
        return json.dumps(dict(arguments), ensure_ascii=False, indent=2, sort_keys=True)
    return str(arguments)


def _format_duration(duration_ms: float) -> str:
    """工具耗时统一用秒展示（0.01s 精度），与状态栏的秒级单位一致。"""
    return f"{duration_ms / 1000:.2f}s"


def _format_token_count(value: int) -> str:
    """token 数：千级以上用 k 缩写（1.2k），千级以下保留原值。"""
    if value < 1000:
        return str(value)
    return f"{value / 1000:.1f}k"


def _result_text(observation: Observation) -> str:
    parts = [observation.content]
    if observation.error:
        parts.append(f"错误: {observation.error}")
    return "\n".join(part for part in parts if part)

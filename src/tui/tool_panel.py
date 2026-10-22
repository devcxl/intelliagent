"""工具调用折叠面板：执行中展开，结束后收成一行摘要（issue #90）。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static

from src.core.tool_pipeline import Observation

TOOL_STATE_LABELS = {"running": "执行中", "success": "成功", "denied": "已拒绝", "error": "失败"}
TOOL_BODY_MAX_LINES = 20
"""工具面板展开正文的最高行数：超出后在面板内滚动，不挤占消息流。"""


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


def _format_arguments(arguments: str | Mapping[str, Any]) -> str:
    if isinstance(arguments, Mapping):
        return json.dumps(dict(arguments), ensure_ascii=False, indent=2, sort_keys=True)
    return str(arguments)


def _format_duration(duration_ms: float) -> str:
    """工具耗时统一用秒展示（0.01s 精度），与状态栏的秒级单位一致。"""
    return f"{duration_ms / 1000:.2f}s"


def _result_text(observation: Observation) -> str:
    parts = [observation.content]
    if observation.error:
        parts.append(f"错误: {observation.error}")
    return "\n".join(part for part in parts if part)

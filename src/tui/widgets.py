"""TUI 组件：消息流、消息单元、工具调用折叠面板、状态栏（ADR 0009 的 pi 最简形态）。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Collapsible, Static

from src.core.agent_events import MessageDelta
from src.core.tool_pipeline import Observation
from src.llm.stream import Error, TextDelta

ROLE_LABELS = {"user": "你", "assistant": "助手", "system": "系统"}
TOOL_STATE_LABELS = {"running": "执行中", "success": "成功", "denied": "已拒绝", "error": "失败"}


class MessageView(Static):
    """一条 Message 的渲染单元（CONTEXT 术语：Message）。

    append_delta 只缓冲增量、不重绘——整步刷新（issue #61）在 finish() 一次性写出；
    issue #63 的流式渲染只需把 append_delta 改成边收边 update。
    """

    def __init__(self, role: str, *, text: str = "", message_id: str | None = None) -> None:
        self.role = role
        self.message_id = message_id
        self._text_parts: list[str] = [text] if text else []
        self._text = text
        super().__init__(self._renderable(), classes=f"message role-{role}")

    @property
    def text(self) -> str:
        """消息正文（不含角色标签），供测试与诊断读取。"""
        return self._text

    def append_delta(self, delta: MessageDelta) -> None:
        """缓冲一次流式增量（issue #63 的流式渲染接口：改为边收边 update 即可）。"""
        if isinstance(delta, TextDelta):
            self._text_parts.append(delta.text)
        elif isinstance(delta, Error):
            self._text_parts.append(f"\n（流式错误：{delta.message}）")
        # ToolCallDelta 不进消息正文：工具调用由 tool_execution_* 事件渲染成折叠面板

    def finish(self) -> None:
        """整步刷新：把缓冲的增量一次性写出。"""
        self._text = "".join(self._text_parts)
        self.update(self._renderable())

    def _renderable(self) -> Text:
        label = ROLE_LABELS.get(self.role, self.role)
        return Text.assemble((f"{label}  ", "bold"), self._text)


class ToolCallPanel(Collapsible):
    """一次工具调用的折叠面板：tool_execution_start 建（执行中态），tool_execution_end 写最终结果。"""

    def __init__(self, tool_call_id: str, name: str, arguments: str | Mapping[str, Any]) -> None:
        self.tool_call_id = tool_call_id
        self.tool_name = name
        self._arguments = arguments
        self._status = "running"
        self._result_text = ""
        self._progress_parts: list[str] = []
        self._body = Static(self._render_body(), classes="tool-body")
        super().__init__(self._body, title=self._render_title(), collapsed=True)

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
        self._body.update(self._render_body())

    def finish(self, observation: Observation) -> None:
        """写最终结果：状态与结果文本落定（整步刷新）。"""
        self._status = observation.status
        self._result_text = _result_text(observation)
        self.title = self._render_title()
        self._body.update(self._render_body())

    def _render_title(self) -> str:
        state = TOOL_STATE_LABELS.get(self._status, self._status)
        return f"{self.tool_name} · {state}"

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


class StatusBar(Static):
    """底部状态栏：工作目录、模型、运行状态（issue #61 验收点）。"""

    def __init__(self, cwd: Path, model: str) -> None:
        super().__init__("", id="status-bar", markup=False)
        self._cwd = cwd
        self._model = model
        self._run_state = "就绪"
        self._refresh()

    def set_run_state(self, state: str) -> None:
        """更新运行状态（就绪/运行中/已完成/已终止/出错/已中止）。"""
        self._run_state = state
        self._refresh()

    @property
    def text(self) -> str:
        """状态栏纯文本，供测试与诊断读取。"""
        return self._render_text()

    def _refresh(self) -> None:
        self.update(self._render_text())

    def _render_text(self) -> str:
        return f"目录 {self._cwd}  模型 {self._model}  状态 {self._run_state}  (ctrl+j 提交)"


def _format_arguments(arguments: str | Mapping[str, Any]) -> str:
    if isinstance(arguments, Mapping):
        return json.dumps(dict(arguments), ensure_ascii=False, indent=2, sort_keys=True)
    return str(arguments)


def _result_text(observation: Observation) -> str:
    parts = [observation.content]
    if observation.error:
        parts.append(f"错误: {observation.error}")
    return "\n".join(part for part in parts if part)

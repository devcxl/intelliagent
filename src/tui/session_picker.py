"""会话列表模态（ADR 0013）：`/resume` 弹出的选择器。

只负责「显示并返回选中 id」，不碰存储与引擎——数据由调用方（app）查好传入，
选中结果经 dismiss 返回 conversation id，取消返回 None。这样模态层不依赖存储，
测试可以直接构造 SessionSummary 验证渲染与选择行为。
"""

from __future__ import annotations

from datetime import datetime, timezone

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from src.runtime.session_view import SessionSummary

UNTITLED = "（未命名会话）"
"""标题尚未生成（首轮未完成）时的显示文案。"""

ID_PREFIX_CHARS = 12
"""列表里的 id 短前缀长度：够区分同目录下的多个会话，又不挤占一行。"""


class SessionPicker(ModalScreen[str | None]):
    """会话选择模态：方向键移动 + Enter 确认，选中返回 conversation id，Esc 取消返回 None。"""

    BINDINGS = [Binding("escape", "cancel", "取消", show=False)]

    CSS = """
    SessionPicker { align: center middle; }
    SessionPicker > Vertical {
        width: 72; height: auto; max-height: 80%;
        border: thick $accent; background: $surface; padding: 1 2;
    }
    SessionPicker .picker-title { width: 1fr; color: $accent; }
    SessionPicker OptionList { height: auto; max-height: 20; }
    SessionPicker .picker-hint { width: 1fr; color: $text-muted; }
    """

    def __init__(self, records: tuple[SessionSummary, ...], *, now: datetime | None = None) -> None:
        super().__init__()
        self._records = records
        self._now = now or datetime.now(timezone.utc).replace(tzinfo=None)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label("选择会话（Enter 打开，Esc 取消）", classes="picker-title")
            if self._records:
                yield OptionList(*[Option(self._label(record), id=record.entry_id) for record in self._records])
            else:
                yield Label("本目录还没有会话", classes="picker-hint")
            yield Label("提示：新开窗口运行即是一段独立会话。", classes="picker-hint")

    def on_mount(self) -> None:
        options = self.query(OptionList)
        if options:
            options.first().focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _label(self, record: SessionSummary) -> str:
        """一项的文案：标题 · 相对时间 · id 短前缀。"""
        title = record.title or UNTITLED
        return f"{title}  ·  {_relative_time(record.created_at, self._now)}  ·  {record.entry_id[:ID_PREFIX_CHARS]}"


def _relative_time(created_at: datetime, now: datetime) -> str:
    """把创建时间压成「刚刚 / N 分钟前 / N 小时前 / N 天前」；超过 30 天显示日期。"""
    seconds = max(int((now - created_at).total_seconds()), 0)
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    if seconds < 30 * 86400:
        return f"{seconds // 86400} 天前"
    return created_at.strftime("%Y-%m-%d")

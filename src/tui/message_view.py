"""单条消息的渲染单元：assistant 走 Markdown 流式，user/system 走角色配色纯文本（issue #91）。

三类消息都不显示角色标签：assistant 用主题前景与 Markdown 结构，user 用 accent、system 用
warning，仅以颜色区分。流式增量沿用「合并到达的增量、只重绘本单元」的成本约束
（issue #63）：同步突发的多个 delta 在一次 flush 中合并为一次 Markdown append。
"""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Markdown, Static
from textual.widgets.markdown import MarkdownStream

from src.core.agent_events import MessageDelta
from src.llm.stream import Error, TextDelta

EMPTY_MESSAGE_PLACEHOLDER = "（无内容）"
"""已收束且没有任何正文的消息占位；仅有工具调用的消息不占位。"""

STREAM_ERROR_TEMPLATE = "\n（流式错误：{message}）"


class MessageView(Vertical):
    """一条 Message 的渲染单元（CONTEXT 术语：Message）。

    assistant 的正文由 Textual Markdown 流式承载，代码块、列表与表格由 Markdown 解析；
    user/system 是纯文本，绝不被当作 Markdown 解析（用户输入里的 ``*`` 保持原样）。
    收束时空消息落占位，流式错误文本随增量落屏。
    """

    def __init__(self, role: str, *, text: str = "", message_id: str | None = None) -> None:
        self.role = role
        self.message_id = message_id
        self._text_parts: list[str] = [text] if text else []
        self._pending: list[str] = [text] if text else []
        self._received_delta = bool(text)
        self._finished = False
        self._flush_scheduled = False
        self._rendered_text = text if role != "assistant" else ""
        self._stream: MarkdownStream | None = None
        self._stop_scheduled = False
        self._write_tasks: set[asyncio.Task[None]] = set()
        if role == "assistant":
            self._markdown: Markdown | None = Markdown("", classes="message-markdown")
            self._plain: Static | None = None
        else:
            self._markdown = None
            self._plain = Static(text, markup=False, classes="message-text")
        super().__init__(classes=f"message role-{role}")

    @property
    def text(self) -> str:
        """消息正文（不含角色标签）：已收到的全部增量拼接，供测试与诊断读取。"""
        return "".join(self._text_parts)

    @property
    def rendered_text(self) -> str:
        """已提交渲染的展示正文（含空态占位）：随 flush 推进，供测试与诊断读取。"""
        return self._rendered_text

    def compose(self) -> ComposeResult:
        if self._markdown is not None:
            yield self._markdown
        elif self._plain is not None:
            yield self._plain

    def on_mount(self) -> None:
        """Markdown 子组件挂载完成后再接上流：先挂载、后写，避免首段被 Markdown 初始化覆盖。"""
        if self._markdown is not None:
            self.call_after_refresh(self._start_stream)

    def append_delta(self, delta: MessageDelta) -> None:
        """收一个流式增量：进缓冲并安排合并重绘，不逐 delta 全量重绘（issue #63）。"""
        self._received_delta = True
        if isinstance(delta, TextDelta):
            self._pending.append(delta.text)
            self._text_parts.append(delta.text)
            self._schedule_flush()
        elif isinstance(delta, Error):
            rendered = STREAM_ERROR_TEMPLATE.format(message=delta.message)
            self._pending.append(rendered)
            self._text_parts.append(rendered)
            self._schedule_flush()
        # ToolCallDelta 不进消息正文：工具调用由 tool_execution_* 事件渲染成折叠面板

    def flush(self) -> None:
        """把缓冲的增量立即提交渲染（幂等；无待渲染内容时不动，避免多余重绘）。

        同步 API：Markdown 的实际 append 是异步的，这里只把合并后的片段交给渲染队列，
        因此 ``flush_pending()`` 之后 await 一次事件循环即可稳定看到内容。
        """
        self._flush_scheduled = False
        if self._markdown is not None:
            if self._stream is None:
                return  # 流尚未就绪：增量留在缓冲，_start_stream 后按序落屏
            self._flush_markdown()
        else:
            self._flush_plain()

    def finish(self) -> None:
        """消息收束：空态占位生效并提交渲染；assistant 的 Markdown 流一并收尾。"""
        self._finished = True
        self.flush()
        self._schedule_stop()

    def settle(self) -> None:
        """收束清算（缺 MessageEnd 的兜底）：缓冲落屏，空消息落空态占位。"""
        self.finish()

    def _start_stream(self) -> None:
        """在 Markdown 子组件挂载后创建流，并落屏此前缓冲的全部增量。"""
        if self._stream is not None or self._markdown is None or not self._markdown.is_mounted:
            return
        self._stream = Markdown.get_stream(self._markdown)
        self.flush()
        if self._finished:
            self._schedule_stop()

    def _schedule_flush(self) -> None:
        if self._flush_scheduled:
            return
        self._flush_scheduled = True
        if not self.call_later(self._flush_soon):
            self._flush_soon()

    def _flush_soon(self) -> None:
        """合并窗口收口（call_later 回调）：一轮事件的增量在此合成一次渲染。"""
        self.flush()

    def _flush_markdown(self) -> None:
        fragment = "".join(self._pending)
        self._pending.clear()
        if fragment:
            self._rendered_text += fragment
            self._write_markdown(fragment)
        elif self._finished and not self._received_delta and not self._rendered_text:
            self._rendered_text = EMPTY_MESSAGE_PLACEHOLDER
            self._write_markdown(EMPTY_MESSAGE_PLACEHOLDER)

    def _flush_plain(self) -> None:
        self._pending.clear()
        display = self._display_text()
        self._rendered_text = display
        if self._plain is not None:
            self._plain.update(display)

    def _write_markdown(self, fragment: str) -> None:
        if self._stream is None:
            return
        task = asyncio.create_task(self._stream.write(fragment))
        self._write_tasks.add(task)
        task.add_done_callback(self._write_tasks.discard)

    def _schedule_stop(self) -> None:
        if not self._finished or self._stream is None or self._stop_scheduled:
            return
        self._stop_scheduled = True
        asyncio.create_task(self._stop_stream())

    async def _stop_stream(self) -> None:
        if self._stream is not None:
            await self._stream.stop()

    def _display_text(self) -> str:
        text = self.text
        if text or not self._finished or self._received_delta:
            return text
        return EMPTY_MESSAGE_PLACEHOLDER

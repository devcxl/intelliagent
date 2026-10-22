"""单条消息的渲染单元：assistant 走 Markdown 流式，user/system 走角色配色纯文本（issue #91）。

三类消息都不显示角色标签：assistant 用主题前景与 Markdown 结构，user 用 accent、system 用
warning，仅以颜色区分。assistant 的写入由一个队列 + 单一后台消费者串行化：队列保证增量顺序，
Textual ``MarkdownStream`` 的排队合并保证同步突发只产生一次 append；消费者在排空队列后显式
``stop()`` Markdown 流，避免写入已停止的流或遗留任务。
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
        self._received_delta = bool(text)
        self._finished = False
        self._rendered_text = text if role != "assistant" else ""
        self._stream: MarkdownStream | None = None
        self._write_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._writer_task: asyncio.Task[None] | None = None
        self._stream_stopping = False
        self._stream_stopped = False
        self._stream_error: BaseException | None = None
        if role == "assistant":
            self._markdown: Markdown | None = Markdown("", classes="message-markdown")
            self._plain: Static | None = None
            if text:
                self._write_queue.put_nowait(text)
        else:
            self._markdown = None
            self._plain = Static(text, markup=False, classes="message-text")
        super().__init__(classes=f"message role-{role}")

    @property
    def text(self) -> str:
        """消息正文（不含角色标签）：已接受的增量拼接，供测试与诊断读取。"""
        return "".join(self._text_parts)

    @property
    def rendered_text(self) -> str:
        """真实已落屏的正文（assistant 直接取 Markdown.source，不会领先于渲染结果）。"""
        if self._markdown is not None:
            return self._markdown.source
        return self._rendered_text

    @property
    def stream_error(self) -> BaseException | None:
        """Markdown 写入/停止过程中记录的首个异常，供诊断与测试断言；正常时为 None。"""
        return self._stream_error

    def compose(self) -> ComposeResult:
        if self._markdown is not None:
            yield self._markdown
        elif self._plain is not None:
            yield self._plain

    def on_mount(self) -> None:
        """Markdown 子组件挂载完成后再接上流：先挂载、后写，避免首段被 Markdown 初始化覆盖。"""
        if self._markdown is not None:
            self.call_after_refresh(self._start_stream)

    async def on_unmount(self) -> None:
        """组件卸载：取消消费者并尽力停止 Markdown 流，不留下 pending 任务或写入已停止的流。"""
        task = self._writer_task
        if task is not None and not task.done():
            task.cancel()
        if task is not None:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:  # 兜底记录消费者异常，避免卸载路径抛出未处理异常
                self._record_stream_error("消费者", exc)
        await self._stop_stream()

    def append_delta(self, delta: MessageDelta) -> None:
        """收一个流式增量：assistant 入队由消费者顺序写入，user/system 直接更新纯文本。"""
        if self._finished:
            # 引擎契约保证 MessageEnd 后不再有增量；拒绝晚到的 delta，避免写已停止的流。
            return
        self._received_delta = True
        if isinstance(delta, TextDelta):
            self._text_parts.append(delta.text)
            self._deliver(delta.text)
        elif isinstance(delta, Error):
            rendered = STREAM_ERROR_TEMPLATE.format(message=delta.message)
            self._text_parts.append(rendered)
            self._deliver(rendered)
        # ToolCallDelta 不进消息正文：工具调用由 tool_execution_* 事件渲染成折叠面板

    def finish(self) -> None:
        """消息收束：只入队一个停止哨兵。

        消费者必须先排空已入队片段，再 await MarkdownStream.stop()，显式建立 write → stop 顺序；
        空消息占位也由消费者在收到哨兵时写入，保证与正文走同一条写入序列。
        """
        if self._finished:
            return
        self._finished = True
        if self._markdown is None:
            self._rendered_text = self._display_text()
            if self._plain is not None:
                self._plain.update(self._rendered_text)
            return
        self._write_queue.put_nowait(None)

    def settle(self) -> None:
        """半程清算（缺 MessageEnd 的兜底）：按收束语义入队占位与停止哨兵。"""
        self.finish()

    def _deliver(self, fragment: str) -> None:
        """把增量交给该消息唯一的写入队列；流未就绪时先排队，消费者启动后按序排空。"""
        if self._markdown is None:
            self._flush_plain()
            return
        self._write_queue.put_nowait(fragment)

    def _flush_plain(self) -> None:
        display = self._display_text()
        self._rendered_text = display
        if self._plain is not None:
            self._plain.update(display)

    def _start_stream(self) -> None:
        """在 Markdown 子组件挂载后创建流与唯一消费者。

        消费者是长生命周期的写入泵，故意不放进 app.workers：``wait_for_complete()`` 会等待
        全部 worker，未结束的消息会永久阻塞该调用。这里自管任务并在 on_unmount 取消、await。
        """
        if self._stream is not None or self._markdown is None or not self._markdown.is_mounted:
            return
        self._stream = Markdown.get_stream(self._markdown)
        self._writer_task = asyncio.create_task(self._consume_writes(), name=f"message-markdown-writer-{id(self)}")

    async def _consume_writes(self) -> None:
        """顺序消费队列：批量取走已入队片段，写完一批后若遇停止哨兵则停止 Markdown 流。"""
        if self._stream is None:
            return
        try:
            while True:
                fragment = await self._write_queue.get()
                if fragment is None:
                    if not self._received_delta:
                        await self._stream.write(EMPTY_MESSAGE_PLACEHOLDER)
                    break
                batch = [fragment]
                stop_after = False
                while True:
                    try:
                        pending = self._write_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if pending is None:
                        stop_after = True
                        break
                    batch.append(pending)
                await self._stream.write("".join(batch))
                if stop_after:
                    break
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 写入失败需记录并收束，不能变成未取回异常
            self._record_stream_error("写入", exc)
        finally:
            await self._stop_stream()

    async def _stop_stream(self) -> None:
        """停止 Markdown 流（幂等）；异常记录到 stream_error 并写日志，不上抛为未取回异常。"""
        stream = self._stream
        if stream is None or self._stream_stopped or self._stream_stopping:
            return
        self._stream_stopping = True
        try:
            await stream.stop()
            self._stream_stopped = True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # 停止失败只影响收尾，记录后由 on_unmount 重试
            self._record_stream_error("停止", exc)
        finally:
            self._stream_stopping = False

    def _record_stream_error(self, phase: str, exc: BaseException) -> None:
        if self._stream_error is None:
            self._stream_error = exc
        self.log.error("Markdown 流%s失败：%s", phase, exc)

    def _display_text(self) -> str:
        text = self.text
        if text or not self._finished or self._received_delta:
            return text
        return EMPTY_MESSAGE_PLACEHOLDER

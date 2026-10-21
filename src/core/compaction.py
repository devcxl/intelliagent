"""投影式压缩（CONTEXT 术语：Compaction）：阈值触发 → turn 边界切点 → LLM 增量摘要 → compaction 记录。

复刻蓝本 docs/pi-engine-principles.md §4：原始记录永不删除，压缩只追加 compaction 记录
（摘要 + first_kept_entry_id + prompt checkpoint）；发给模型的上下文每次请求从 storage.projection 现算，
重启后投影不含被压缩 entry。

token 计数（TokenCounter）：优先用 provider 真实 usage（覆盖请求消息前缀），基线之后新增消息按
chars/4 估算——绝不跨轮累计（旧 ContextManager 误触发的根因）；基线失配（压缩重建投影）退回整体估算。

切点语义（findCutPoint）：从尾部累计到 keepRecentTokens 定预算耗尽点，吸附到有效切点——tool 结果
永远不是切点（与它的 assistant tool_call 同侧保留）；切在 turn 中间即 split turn，其前缀单独总结。

接线：Compactor.hooks() 提供 prepareRequest / prepareNextTurn 两个 turn hook（ADR 0010）。
prepareRequest 必须先于注入类 hook 执行（注册顺序保证）：它把引擎新增 Message 落库并整体替换请求视图，
注入类 hook 的临时消息因此不落库、不进投影。
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from src.core.compaction_prompts import (
    SPLIT_TURN_MARKER,
    SUMMARIZATION_PROMPT,
    SUMMARIZATION_SYSTEM_PROMPT,
    TURN_PREFIX_SUMMARIZATION_PROMPT,
    UPDATE_SUMMARIZATION_PROMPT,
)
from src.core.turn_hooks import (
    NextTurnContext,
    NextTurnUpdate,
    PrepareNextTurnHook,
    PrepareRequestHook,
    RequestContext,
)
from src.llm.stream import (
    ChatMessage,
    Done,
    LLMClient,
    LLMEvent,
    StopReason,
    StreamRequest,
    TextDelta,
    ToolCallDelta,
    Usage,
)
from src.plugins.storage import ENTRY_TYPE_MESSAGE, Entry, MessagePayload, StorageStore

NO_PRIOR_HISTORY = "No prior history."
"""split turn 且无可摘要历史时的占位历史文本（pi compact 同值）。"""


class CompactionError(RuntimeError):
    """压缩失败：摘要在有限重试内拿不到可接受结果，或摘要流违约。"""


@dataclass(frozen=True)
class CutPoint:
    """压缩切点（pi CutPointResult）：保留段起点、split turn 的 turn 起点与标记。"""

    first_kept_index: int
    turn_start_index: int | None = None
    is_split_turn: bool = False


@dataclass(frozen=True)
class CompactionOutcome:
    """一次压缩的收束结果：写入的 compaction 记录与其语义标记。"""

    entry_id: str
    summary: str
    first_kept_entry_id: str
    is_split_turn: bool


def estimate_tokens(message: ChatMessage) -> int:
    """单条消息的 token 估算（pi estimateTokens）：正文与 tool_call 的 name/arguments 按 chars/4。"""
    chars = len(str(message.get("content") or ""))
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        chars += len(str(function.get("name") or "")) + len(str(function.get("arguments") or ""))
    return math.ceil(chars / 4)


class TokenCounter:
    """上下文 token 计数：真实 usage 基线 + 基线外消息的 chars/4 估算（pi estimateContextTokens）。

    基线是最近一次响应的 provider 真实 usage 与其覆盖的消息前缀；新响应重新定基线而不累计。
    """

    def __init__(self) -> None:
        self._baseline: tuple[int, tuple[ChatMessage, ...]] | None = None

    def record(self, usage: Usage | None, covered: Sequence[ChatMessage]) -> None:
        """记录一次模型响应的真实 usage 与它覆盖的消息前缀；无有效 usage 时清除基线。"""
        if usage is None or usage.prompt_tokens <= 0:
            self._baseline = None
            return
        self._baseline = (usage.prompt_tokens, tuple(dict(message) for message in covered))

    def estimate(self, messages: Sequence[ChatMessage]) -> int:
        """估算消息列表的上下文 token：基线 + 基线外消息估算；基线失配退回整体 chars/4 估算。"""
        if self._baseline is not None:
            base, covered = self._baseline
            if _is_prefix(covered, messages):
                return base + sum(estimate_tokens(message) for message in messages[len(covered) :])
        return sum(estimate_tokens(message) for message in messages)


class UsageRecordingClient:
    """LLMClient 装饰器：观察每条流的 Done.usage 喂给 TokenCounter，事件原样透传。

    引擎（src/core/engine.py）不感知压缩；usage 消费靠这个装饰器与引擎之间的 seam。
    """

    def __init__(self, inner: LLMClient, counter: TokenCounter) -> None:
        self._inner = inner
        self._counter = counter

    def stream(self, request: StreamRequest, *, abort: threading.Event | None = None) -> Iterator[LLMEvent]:
        for event in self._inner.stream(request, abort=abort):
            if isinstance(event, Done):
                self._counter.record(event.usage, request.messages)
            yield event


def find_cut_point(messages: Sequence[ChatMessage], keep_recent_tokens: int) -> CutPoint | None:
    """在消息序列上选压缩切点（pi findCutPoint）。

    从尾部按估算累计到 keepRecentTokens 定预算耗尽点，再吸附到有效切点：tool 结果永远不是切点
    （必须与它的 assistant tool_call 同侧保留），取预算点之后第一个 user/assistant；预算被尾部
    tool 结果独占时退到最后一个有效切点（保配对优先于保预算）。切点不是 user 消息即切在 turn
    中间（split turn）：turn 起点之前的完整 turn 进历史摘要，起点到切点的前缀单独总结。
    """
    valid = [index for index, message in enumerate(messages) if message.get("role") != "tool"]
    if not valid:
        return None
    exhaustion: int | None = None
    accumulated = 0
    for index in range(len(messages) - 1, -1, -1):
        accumulated += estimate_tokens(messages[index])
        if accumulated >= keep_recent_tokens:
            exhaustion = index
            break
    if exhaustion is None:
        first_kept = valid[0]
    else:
        first_kept = next((index for index in valid if index >= exhaustion), valid[-1])
    if messages[first_kept].get("role") == "user":
        return CutPoint(first_kept_index=first_kept)
    turn_start = _find_turn_start(messages, first_kept)
    if turn_start is None:
        return CutPoint(first_kept_index=first_kept)
    return CutPoint(first_kept_index=first_kept, turn_start_index=turn_start, is_split_turn=True)


def _find_turn_start(messages: Sequence[ChatMessage], entry_index: int) -> int | None:
    """向前找切点所在 turn 的起点（pi findTurnStartIndex）：最近的前导 user 消息。"""
    for index in range(entry_index - 1, -1, -1):
        if messages[index].get("role") == "user":
            return index
    return None


def message_payload(message: ChatMessage) -> MessagePayload:
    """引擎 Message → message entry 的 payload（CONTEXT：Message 经 entry 抽象落库）。"""
    tool_calls = [dict(call) for call in message.get("tool_calls") or []]
    return MessagePayload(
        role=str(message.get("role") or ""),
        content=str(message.get("content") or ""),
        tool_call_id=str(message["tool_call_id"]) if message.get("tool_call_id") else None,
        tool_name=str(message["name"]) if message.get("name") else None,
        tool_calls=tool_calls or None,
    )


def entry_message(entry: Entry) -> ChatMessage:
    """message entry → 发给模型的消息（投影重建的最小映射）。"""
    payload = MessagePayload.model_validate(entry.payload)
    message: ChatMessage = {"role": payload.role, "content": payload.content}
    if payload.tool_calls is not None:
        message["tool_calls"] = payload.tool_calls
    if payload.tool_call_id is not None:
        message["tool_call_id"] = payload.tool_call_id
    if payload.tool_name is not None:
        message["name"] = payload.tool_name
    return message


def summary_message(summary: str) -> ChatMessage:
    """compaction 摘要 → 发给模型的消息（pi：compactionSummary 折叠为带 <summary> 包装的 user 消息）。"""
    return {"role": "user", "content": f"<summary>\n{summary}\n</summary>"}


def serialize_conversation(messages: Sequence[ChatMessage]) -> str:
    """把消息序列化为摘要 prompt 的对话文本：role + 正文 + tool_call 名称与参数。"""
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        lines.append(f"{role}: {content}" if content else f"{role}:")
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            lines.append(f"  tool_call {function.get('name')}({function.get('arguments')})")
    return "\n".join(lines)


class Compactor:
    """投影式压缩执行者（CONTEXT 术语：Compaction）：持久化 Message、现算 Projection、阈值压缩。

    依赖显式注入：摘要用 LLMClient（传原始客户端——摘要请求的 usage 不属于会话上下文计数）、
    StorageStore、TokenCounter（与包住引擎的 UsageRecordingClient 共享同一实例）。
    resume_entry_id 续接既有分支（重启场景）：之后的 Message 从该 leaf 追加、投影从该 leaf 现算。
    """

    def __init__(
        self,
        llm: LLMClient,
        store: StorageStore,
        *,
        model: str,
        counter: TokenCounter,
        context_window: int,
        reserve_tokens: int = 16_384,
        keep_recent_tokens: int = 20_000,
        max_summary_attempts: int = 3,
        resume_entry_id: str | None = None,
    ) -> None:
        self._llm = llm
        self._store = store
        self._model = model
        self._counter = counter
        self._context_window = context_window
        self._reserve_tokens = reserve_tokens
        self._keep_recent_tokens = keep_recent_tokens
        self._max_summary_attempts = max_summary_attempts
        self._tip: str | None = resume_entry_id
        self._persisted = 0
        self._checkpoint: dict[str, Any] = {"system_prompt": "", "tools": [], "model": model}

    @property
    def leaf_entry_id(self) -> str | None:
        """当前分支的 leaf entry（投影查询与重启续接的锚点）。"""
        return self._tip

    def hooks(self) -> tuple[PrepareRequestHook, PrepareNextTurnHook]:
        """turn 边界 hook 能力提供者：prepareRequest 现算投影、prepareNextTurn 阈值压缩。"""
        return (
            PrepareRequestHook(callback=self.prepare_request),
            PrepareNextTurnHook(callback=self.prepare_next_turn),
        )

    async def sync_messages(self, messages: Sequence[ChatMessage]) -> None:
        """把 Conversation 记录中尚未落库的 Message 追加为 message entry（append-only 链）。

        messages 是引擎 Conversation 的全量记录（append-only）：与已落库序号对齐，只追加新尾部；
        hook 注入的临时视图不在记录中，因此不会落库。
        """
        for message in list(messages)[self._persisted :]:
            entry = await self._store.append_message(message_payload(message), parent_id=self._tip)
            self._tip = entry.id
            self._persisted += 1

    async def projection_messages(self) -> list[ChatMessage]:
        """现算投影（CONTEXT 术语：Projection）：摘要消息 + 保留段 entry 重建的消息序列。

        只有 message entry 进入模型视图（pi：custom 类 entry 不进 LLM 上下文）。
        """
        if self._tip is None:
            return []
        projection = await self._store.projection(self._tip)
        kept = [entry_message(entry) for entry in _message_entries(projection.entries)]
        if projection.compaction is None:
            return kept
        return [summary_message(projection.compaction.summary), *kept]

    async def context_tokens(self) -> int:
        """当前投影的上下文 token 估算。"""
        return self._counter.estimate(await self.projection_messages())

    async def should_compact(self) -> bool:
        """阈值判定（pi shouldCompact）：当前 token > contextWindow - reserveTokens。"""
        return await self.context_tokens() > self._context_window - self._reserve_tokens

    async def compact(self) -> CompactionOutcome | None:
        """执行一次压缩：选切点 → LLM 增量摘要 → 追加 compaction 记录；无可压缩内容返回 None。

        被截断（stop=length）、调用工具或空的摘要拒绝并重试（有限次），耗尽抛 CompactionError。
        """
        if self._tip is None:
            return None
        projection = await self._store.projection(self._tip)
        kept_entries = _message_entries(projection.entries)
        kept = [entry_message(entry) for entry in kept_entries]
        cut = find_cut_point(kept, self._keep_recent_tokens)
        if cut is None:
            return None
        history, turn_prefix = self._split_at_cut(kept, cut)
        if not history and not turn_prefix:
            return None
        previous = projection.compaction.summary if projection.compaction is not None else None
        summary = await self._generate_summary(history, turn_prefix, previous)
        record = await self._store.append_compaction(
            summary=summary,
            first_kept_entry_id=kept_entries[cut.first_kept_index].id,
            prompt_checkpoint=dict(self._checkpoint),
            parent_id=self._tip,
        )
        self._tip = record.entry_id
        return CompactionOutcome(
            entry_id=record.entry_id,
            summary=summary,
            first_kept_entry_id=record.first_kept_entry_id,
            is_split_turn=cut.is_split_turn,
        )

    async def prepare_request(self, request: RequestContext) -> None:
        """prepareRequest 挂载：落库引擎新增 Message，请求视图整体替换为现算投影（pi §3.2）。

        同时把本次请求的 system prompt 与工具清单快照为 prompt checkpoint 的取材。
        本 hook 必须先于注入类 hook 执行（注册顺序保证）：注入的临时消息不落库、不进投影。
        """
        await self.sync_messages(request.messages)
        self._checkpoint = self._snapshot_checkpoint(request)
        request.messages = await self.projection_messages()

    async def prepare_next_turn(self, context: NextTurnContext) -> NextTurnUpdate | None:
        """prepareNextTurn 挂载：turn 边界落库刚完成的 turn，超阈值即压缩（pi 自动压缩触发点）。"""
        await self.sync_messages(context.messages)
        if await self.should_compact():
            await self.compact()
        return None

    @staticmethod
    def _split_at_cut(kept: Sequence[ChatMessage], cut: CutPoint) -> tuple[list[ChatMessage], list[ChatMessage]]:
        """按切点把可压缩段分成完整 turn 的历史段与 split turn 的前缀段。"""
        if cut.is_split_turn and cut.turn_start_index is not None:
            return list(kept[: cut.turn_start_index]), list(kept[cut.turn_start_index : cut.first_kept_index])
        return list(kept[: cut.first_kept_index]), []

    async def _generate_summary(
        self, history: Sequence[ChatMessage], turn_prefix: Sequence[ChatMessage], previous: str | None
    ) -> str:
        """生成合并摘要：历史段走增量摘要；split turn 前缀用独立 prompt 单独总结（pi compact）。"""
        if not turn_prefix:
            return await self._generate(history, previous, turn_prefix=False)
        history_text = await self._generate(history, previous, turn_prefix=False) if history else NO_PRIOR_HISTORY
        prefix_text = await self._generate(turn_prefix, None, turn_prefix=True)
        return f"{history_text}\n\n---\n\n{SPLIT_TURN_MARKER}\n\n{prefix_text}"

    async def _generate(self, messages: Sequence[ChatMessage], previous: str | None, *, turn_prefix: bool) -> str:
        """跑有限次摘要尝试：拒绝被截断/调工具/空的摘要，重试耗尽抛 CompactionError。"""
        request = self._summary_request(messages, previous, turn_prefix=turn_prefix)
        for _ in range(self._max_summary_attempts):
            summary = self._accepted_summary(request)
            if summary is not None:
                return summary
        raise CompactionError(f"compaction summarization failed after {self._max_summary_attempts} attempts")

    def _accepted_summary(self, request: StreamRequest) -> str | None:
        """消费一条摘要流：截断（stop=length）、调工具或空的摘要拒绝（None 即重试），error/aborted 硬失败。"""
        parts: list[str] = []
        tool_call_seen = False
        stop_reason: StopReason | None = None
        for event in self._llm.stream(request):
            if isinstance(event, TextDelta):
                parts.append(event.text)
            elif isinstance(event, ToolCallDelta):
                tool_call_seen = True
            elif isinstance(event, Done):
                stop_reason = event.stop_reason
        if stop_reason is None:
            raise CompactionError("summarization stream ended without Done")
        if stop_reason in ("error", "aborted"):
            raise CompactionError(f"summarization failed with stop reason '{stop_reason}'")
        text = "".join(parts)
        if stop_reason == "length" or tool_call_seen or not text:
            return None
        return text

    def _summary_request(
        self, messages: Sequence[ChatMessage], previous: str | None, *, turn_prefix: bool
    ) -> StreamRequest:
        """构造摘要请求：会话序列化进单条 user 消息，previous 携带做增量更新（pi generateSummary）。"""
        prompt = f"<conversation>\n{serialize_conversation(messages)}\n</conversation>\n\n"
        if previous is not None:
            prompt += f"<previous_summary>\n{previous}\n</previous_summary>\n\n"
        if turn_prefix:
            prompt += TURN_PREFIX_SUMMARIZATION_PROMPT
        else:
            prompt += UPDATE_SUMMARIZATION_PROMPT if previous is not None else SUMMARIZATION_PROMPT
        max_tokens = int((0.5 if turn_prefix else 0.8) * self._reserve_tokens)
        return StreamRequest(
            model=self._model,
            messages=[{"role": "system", "content": SUMMARIZATION_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )

    @staticmethod
    def _snapshot_checkpoint(request: RequestContext) -> dict[str, Any]:
        """压缩边界处的 prompt 快照：system prompt 全文 + 工具名清单 + 模型。"""
        system_prompt = "\n".join(
            str(message.get("content") or "") for message in request.messages if message.get("role") == "system"
        )
        tools = [str((tool.get("function") or {}).get("name") or "") for tool in request.tools]
        return {"system_prompt": system_prompt, "tools": tools, "model": request.model}


def _is_prefix(covered: Sequence[ChatMessage], messages: Sequence[ChatMessage]) -> bool:
    return len(covered) <= len(messages) and all(a == b for a, b in zip(covered, messages))


def _message_entries(entries: Sequence[Entry]) -> list[Entry]:
    """保留段中进入模型视图的 message entry（pi：custom 类 entry 不进 LLM 上下文）。"""
    return [entry for entry in entries if entry.type == ENTRY_TYPE_MESSAGE]

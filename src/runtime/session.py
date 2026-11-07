"""会话选择与标题生成（ADR 0013）：启动期 -c / -s 解析 + 首轮结束后的标题落库。

职责边界：
- 本模块只做「哪一段会话」与「会话叫什么」，不构造 Engine，也不碰 UI；
- TUI 与 headless 共用同一套选择语义（组合根归 runtime 层，避免两个前端各写一份）；
- 标题是追加的 conversation_title entry：entries 表有拒绝 UPDATE 的触发器，事后改名不可能。

选择语义（ADR 0013）：

- ``conversation_id`` 显式给出：必须已存在，否则启动失败——静默新建会让用户以为续上了上下文；
- ``resume_last``：取本 workspace 最近创建的会话，没有则等同新建；
- 都不给：新建会话（id 形如 ``tui-{hex}`` / ``headless-{hex}``）。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import uuid4

from src.core.async_stream import iterate_in_thread
from src.core.compaction_prompts import TITLE_PROMPT
from src.llm.stream import ChatMessage, Done, LLMClient, StreamRequest, TextDelta
from src.plugins.storage import ENTRY_TYPE_CONVERSATION, ConversationRecord, StorageStore
from src.plugins.storage.errors import StorageError

TITLE_MAX_TOKENS = 64
"""标题生成的输出上限：一行短标题足够。"""

TITLE_TIMEOUT_SECONDS = 5.0
"""标题生成的等待上限；超时静默回退到首条 user 消息截断。"""

TITLE_FALLBACK_CHARS = 40
"""LLM 标题不可用时的兜底长度。"""


class SessionError(Exception):
    """会话选择失败：指定的会话不存在，或存储插件缺席导致无法恢复。"""


@dataclass(frozen=True)
class SessionSelection:
    """启动期选定的会话：id 与是否续接既有记录。

    Attributes:
        conversation_id: 会话根 entry id。
        resume: True 表示续接该会话的最新 leaf；False 表示要求该会话尚无消息记录。
        title: 已有标题（恢复时用于提示），新建时为 None。
    """

    conversation_id: str
    resume: bool
    title: str | None = None


def new_conversation_id(prefix: str) -> str:
    """生成会话 id：``{prefix}-{uuid4().hex}``，与 headless 既有命名一致。"""
    return f"{prefix}-{uuid4().hex}"


async def resolve_session(
    store: StorageStore | None,
    *,
    workspace: str,
    prefix: str,
    resume_last: bool = False,
    conversation_id: str | None = None,
) -> SessionSelection:
    """按 -c / -s / 缺省新建 三种意图解析出本次运行的会话。

    Args:
        store: storage 插件提供的存储；None 表示插件未启用，此时只有新建可用。
        workspace: 启动目录（已 resolve），用于按项目隔离会话列表。
        prefix: 新会话 id 前缀（``tui`` / ``headless``）。
        resume_last: 是否恢复本 workspace 最近创建的会话。
        conversation_id: 显式指定的会话 id。

    Raises:
        SessionError: 指定或要求恢复会话但存储缺席，或指定 id 不存在/不是会话根。
    """
    if conversation_id is not None:
        if store is None:
            raise SessionError("storage 插件未启用，无法打开指定会话（plugins.storage.enabled 需为 true）")
        await _require_conversation(store, conversation_id)
        return SessionSelection(
            conversation_id=conversation_id,
            resume=True,
            title=await store.conversation_title(conversation_id),
        )
    if resume_last:
        if store is None:
            raise SessionError("storage 插件未启用，无法恢复上次会话（plugins.storage.enabled 需为 true）")
        latest = await _latest_conversation(store, workspace)
        if latest is not None:
            return SessionSelection(conversation_id=latest.entry_id, resume=True, title=latest.title)
    selected = new_conversation_id(prefix)
    if store is not None:
        await store.ensure_conversation(selected, workspace=workspace)
    return SessionSelection(conversation_id=selected, resume=False)


async def _require_conversation(store: StorageStore, conversation_id: str) -> None:
    """校验指定 id 是一段存在的会话根；否则抛可诊断的 SessionError。"""
    entry = await store.get_entry(conversation_id)
    if entry is None:
        raise SessionError(f"会话 '{conversation_id}' 不存在")
    if entry.type != ENTRY_TYPE_CONVERSATION:
        raise SessionError(f"entry '{conversation_id}' 不是会话根（type '{entry.type}'）")


async def _latest_conversation(store: StorageStore, workspace: str) -> ConversationRecord | None:
    """取本 workspace 最近创建的会话；没有时返回 None。"""
    conversations = await store.list_conversations(workspace=workspace)
    return conversations[0] if conversations else None


async def ensure_conversation_title(
    llm: LLMClient,
    store: StorageStore | None,
    *,
    conversation_id: str,
    messages: Sequence[ChatMessage],
    model: str,
) -> str | None:
    """首轮结束后生成并落库会话标题；已有标题或无法生成时返回现有值/None。

    幂等：标题已存在即直接返回，调用方无需自己记录「是否已生成」。
    失败路径全部静默——标题是锦上添花，不能拖慢或打断对话。
    """
    if store is None:
        return None
    existing = await store.conversation_title(conversation_id)
    if existing is not None:
        return existing
    first_user = _first_user_text(messages)
    if not first_user:
        return None
    title = await _generate_title(llm, model=model, first_user=first_user)
    try:
        await store.append_conversation_title(conversation_id, title)
    except StorageError:
        return None
    return title


def _first_user_text(messages: Sequence[ChatMessage]) -> str:
    """取首条 user 消息正文（标题生成与兜底的共同输入）。"""
    for message in messages:
        if message.get("role") == "user":
            return str(message.get("content") or "").strip()
    return ""


def fallback_title(text: str) -> str:
    """兜底标题：首条 user 消息压成单行并截断。"""
    collapsed = " ".join(text.split())
    return collapsed[:TITLE_FALLBACK_CHARS] or "未命名会话"


async def _generate_title(llm: LLMClient, *, model: str, first_user: str) -> str:
    """单发一次模型请求生成标题；任何失败/超时都回退到 fallback_title。"""
    request = StreamRequest(
        model=model,
        messages=[
            {"role": "system", "content": TITLE_PROMPT},
            {"role": "user", "content": first_user[:2000]},
        ],
        max_tokens=TITLE_MAX_TOKENS,
    )
    try:
        text = await asyncio.wait_for(_collect_text(llm, request), timeout=TITLE_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 - 标题是锦上添花：超时、网络、解析失败都静默回退
        text = ""
    cleaned = " ".join(text.strip().strip("\"'“”「」").split())
    return cleaned[:60] or fallback_title(first_user)


async def _collect_text(llm: LLMClient, request: StreamRequest) -> str:
    """消费一条流并拼出文本；stop_reason 非 stop 时视为失败（返回空串）。"""
    parts: list[str] = []
    stop_reason: str | None = None
    abort = threading.Event()
    async for event in iterate_in_thread(llm.stream(request, abort=abort)):
        if isinstance(event, TextDelta):
            parts.append(event.text)
        elif isinstance(event, Done):
            stop_reason = event.stop_reason
    if stop_reason != "stop":
        return ""
    return "".join(parts)

"""ChatMessage 与存储 entry payload 的映射（存储 schema 归 storage 插件，core 不感知）。

从 core/compaction.py 倒置而来（PR #77 审查 Standards medium）：映射属于存储 schema，
随 storage 插件演进；core 经 CompactionStore Protocol 的高层方法使用存储。
"""

from __future__ import annotations

from src.plugins.storage.records import ENTRY_TYPE_MESSAGE, Entry, MessagePayload

ChatMessage = dict[str, object]


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


def message_entries(entries: list[Entry]) -> list[Entry]:
    """保留段中进入模型视图的 message entry（pi：custom 类 entry 不进 LLM 上下文）。"""
    return [entry for entry in entries if entry.type == ENTRY_TYPE_MESSAGE]

#!/usr/bin/env python3
"""CLI 输出展示（纯函数，无副作用）。"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable


def format_event(event: dict[str, Any]) -> None:
    """格式化并打印一个事件。"""
    t = event["type"]
    i = event["iteration"]
    data = event["data"]

    if t == "thought":
        content = data.get("content", "")
        if content:
            print(f"[思考 #{i}] {content}")

    elif t == "action":
        tool_name = data["tool"]
        tool_args = data["args"]
        args_str = json.dumps(tool_args, ensure_ascii=False)
        print(f"[行动 #{i}] {tool_name}({args_str})")

    elif t == "observation":
        obs = data
        status = obs.get("status", "?")
        result = obs.get("result", "")
        if isinstance(result, str) and len(result) > 200:
            result = result[:200] + "..."
        print(f"[观察 #{i}] {status}: {result}")

    elif t == "answer":
        answer = data["answer"]
        print(f"\n{'=' * 60}")
        print(f"答案: {answer}")
        print(f"{'=' * 60}\n")


def format_conversation_header(
    history_count: int,
    conversation_id: str,
    is_new: bool,
) -> None:
    """打印 Conversation 头部信息。"""
    if is_new:
        print(f"[新] Conversation: {conversation_id}")
    else:
        print(f"[继续] Conversation: {conversation_id}")

    if history_count > 0:
        print(f"（已加载 {history_count} 条历史消息作为上下文）")
    print()


def format_history_conversation(conversation: dict[str, Any], msg_count: int) -> None:
    """格式化打印一个历史 Conversation。"""
    print(f"  ID:     {conversation['id']}")
    print(f"  标题:   {conversation['title'] or '(无)'}")
    print(f"  状态:   {conversation['status']}")
    print(f"  消息数: {msg_count}")
    print(f"  更新:   {conversation['updated_at']}")
    print(f"  {'─' * 40}")


async def show_history(
    conversations: list[dict[str, Any]],
    get_msg_count: Callable[[str], Awaitable[int]],
) -> None:
    """展示所有历史 Conversation。"""
    if not conversations:
        print("没有历史 Conversation。")
        return

    print(f"\n{'=' * 60}")
    print(f"历史 Conversation 列表（共 {len(conversations)} 个）")
    print(f"{'=' * 60}\n")

    for conversation in conversations:
        msg_count = await get_msg_count(conversation["id"])
        format_history_conversation(conversation, msg_count)


def show_save_info(conversation_id: str) -> None:
    """打印保存信息。"""
    print(f"已保存到 Conversation: {conversation_id}")
    print(f"下次继续请使用: python -m src.main --session {conversation_id}")

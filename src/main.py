#!/usr/bin/env python3
"""
IntelliAgent CLI 入口 — 支持 Conversation 持久化。

用法：
    # 开启新 Conversation
    python -m src.main "你的任务描述"

    # 继续上一次 Conversation（加载历史上下文）
    python -m src.main --resume "后续任务"

    # 查看所有历史 Conversation
    python -m src.main --history

    # 指定 Conversation ID 继续（--session 为兼容别名）
    python -m src.main --session <session_id> "新任务"
"""

from __future__ import annotations

import asyncio
import sys

from src.runtime import ConversationOrchestrator
from src.cli.parser import build_parser, parse_args
from src.cli.presenter import (
    format_conversation_header,
    format_event,
    show_history,
)


async def main(
    task: str,
    session_id: str | None = None,
    resume: bool = False,
    list_history: bool = False,
) -> None:
    orchestrator = ConversationOrchestrator()
    await orchestrator.initialize()

    if list_history:
        conversations = await orchestrator.list_conversations()
        await show_history(conversations, orchestrator.get_message_count)
        return

    conversation_id, history_context = await orchestrator.setup_conversation(task, session_id, resume)
    for warning in orchestrator.warnings:
        print(f"⚠️  {warning}")
    await orchestrator.save_message("user", task)

    history_count = await orchestrator.get_message_count(conversation_id)
    format_conversation_header(task, history_count, conversation_id, orchestrator.is_new)

    assistant_content = ""
    async for event in orchestrator.execute(task, history_context=history_context):
        format_event(event)
        if event["type"] == "answer":
            assistant_content = event["data"]["answer"]

    if assistant_content:
        await orchestrator.save_message("assistant", assistant_content)


# ======================================================================
# CLI 入口
# ======================================================================
if __name__ == "__main__":
    args = parse_args()

    task_text = " ".join(args.task) if args.task else ""
    if not task_text and not args.history:
        build_parser().print_help()
        print("\n❌ 请提供任务描述，或使用 --history 查看历史 Conversation。")
        sys.exit(1)

    asyncio.run(
        main(
            task=task_text,
            session_id=args.session,
            resume=args.resume,
            list_history=args.history,
        )
    )

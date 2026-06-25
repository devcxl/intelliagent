#!/usr/bin/env python3
"""
IntelliAgent CLI 入口 — 多轮对话循环。

用法：
    # 开启新对话
    python -m src.main

    # 继续上一次对话（加载历史上下文）
    python -m src.main --resume

    # 查看所有历史 Conversation
    python -m src.main --history

    # 指定 Conversation ID 继续
    python -m src.main --session <session_id>

交互命令：
    /exit  — 退出对话
    /help  — 显示帮助
"""

from __future__ import annotations

import asyncio
import sys

from src.cli.parser import build_parser, parse_args
from src.cli.presenter import (
    format_conversation_header,
    format_event,
    show_history,
    show_save_info,
)
from src.runtime import AgentRuntime

_PROMPT = "\n> "


async def _run_single_turn(
    runtime: AgentRuntime,
    user_input: str,
) -> str | None:
    """执行一轮对话，返回 assistant 的完整回复内容。"""
    assistant_content = ""
    async for event in runtime.execute(user_input):
        format_event(event)
        if event["type"] == "answer":
            assistant_content = event["data"]["answer"]

    return assistant_content if assistant_content else None


async def _repl_loop(
    runtime: AgentRuntime,
) -> None:
    """多轮对话循环，读取用户输入并逐轮执行。"""
    while True:
        try:
            user_input = input(_PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        if user_input == "/exit":
            break

        if user_input == "/help":
            print("命令：")
            print("  /exit  — 退出对话")
            print("  /help  — 显示此帮助")
            print("  直接输入任务描述即可与 AI 对话")
            continue

        await _run_single_turn(runtime, user_input)


async def main(
    session_id: str | None = None,
    resume: bool = False,
    list_history: bool = False,
) -> None:
    runtime = AgentRuntime()
    await runtime.initialize()

    if list_history:
        conversations = await runtime.list_conversations()
        await show_history(conversations, runtime.get_message_count)
        return

    conversation_id = await runtime.setup_conversation(task="", session_id=session_id, resume=resume)
    for warning in runtime.warnings:
        print(f"⚠️  {warning}")

    history_count = await runtime.get_message_count(conversation_id)
    format_conversation_header(history_count, conversation_id, runtime.is_new)

    await _repl_loop(runtime)

    await runtime.shutdown()
    show_save_info(conversation_id)


# ======================================================================
# CLI 入口
# ======================================================================
if __name__ == "__main__":
    args = parse_args()

    task_text = " ".join(args.task) if args.task else ""
    if task_text and not args.history:
        build_parser().print_help()
        print("\n❌ 多轮对话模式不支持命令行传入任务。请直接运行 python -m src.main 进入交互模式。")
        sys.exit(1)

    asyncio.run(
        main(
            session_id=args.session,
            resume=args.resume,
            list_history=args.history,
        )
    )

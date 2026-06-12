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

import argparse
import asyncio
import json
import sys
import time

from src.config.settings import get_settings
from src.core.context_manager import ContextManager
from src.db import DatabaseManager
from src.runtime import AgentRuntime


# ======================================================================
# 主逻辑
# ======================================================================
async def main(
    task: str,
    session_id: str | None = None,
    resume: bool = False,
    list_history: bool = False,
) -> None:
    settings = get_settings()

    # ---- 初始化数据库 ----
    db_url = settings.DATABASE_URL
    db_manager = DatabaseManager(db_url)
    await db_manager.initialize()

    # ---- 列出历史 Conversation ----
    if list_history:
        await _show_history(db_manager)
        return

    # ---- 确定 Conversation ID ----
    conversation_id: str
    if session_id:
        # --session 是 CLI 兼容参数，内部统一使用 Conversation。
        existing = await db_manager.get_conversation(session_id)
        if existing is None:
            print(f"⚠️  Conversation {session_id} 不存在，将创建新 Conversation。")
            conversation_id = session_id
            await db_manager.create_conversation(
                conversation_id, title=task[:80], task=task,
            )
        else:
            conversation_id = session_id
            await db_manager.update_conversation(
                conversation_id, status="running",
            )
    elif resume:
        # 继续最近一个 Conversation
        latest = await db_manager.get_latest_conversation()
        if latest:
            conversation_id = latest["id"]
            await db_manager.update_conversation(
                conversation_id, status="running",
            )
            print(f"📋 继续 Conversation: {conversation_id} ({latest['title']})")
        else:
            print("⚠️  没有历史 Conversation，将创建新 Conversation。")
            conversation_id = f"conv-{int(time.time() * 1000)}"
            await db_manager.create_conversation(
                conversation_id, title=task[:80], task=task,
            )
    else:
        # 创建全新的 Conversation
        conversation_id = f"conv-{int(time.time() * 1000)}"
        await db_manager.create_conversation(
            conversation_id, title=task[:80], task=task,
        )
        print(f"🆕 新 Conversation: {conversation_id}")

    # ---- 加载历史消息，构建上下文 ----
    history_messages = await db_manager.get_messages(conversation_id)
    history_context = ContextManager.build_history_context(history_messages)

    # ---- 初始化引擎 ----
    engine = AgentRuntime(settings).create_engine()

    # ---- 保存用户消息 ----
    await db_manager.save_message(conversation_id, "user", task)

    # ---- 创建运行记录 ----
    run_id = f"run-{int(time.time() * 1000)}"
    await db_manager.create_run(
        run_id=run_id,
        conversation_id=conversation_id,
        task_snapshot=task,
        status="running",
    )

    # ---- 执行引擎 ----
    print(f"\n{'='*60}")
    print(f"任务: {task}")
    if history_messages:
        print(f"（已加载 {len(history_messages)} 条历史消息作为上下文）")
    print(f"{'='*60}\n")

    assistant_content = ""
    seq = 0

    async for event in engine.iter_steps(task, history_context=history_context):
        t = event["type"]
        i = event["iteration"]
        data = event["data"]
        seq += 1

        if t == "thought":
            content = data.get("content", "")
            has_tools = data.get("has_tool_calls", False)
            if content:
                print(f"[思考 #{i}] {content}")
            # 保存思考内容到执行轨迹
            await db_manager.save_trace(
                trace_id=f"trace-{run_id}-{seq}",
                run_id=run_id,
                iteration=i,
                trace_type="thought",
                data={"content": content},
            )

        elif t == "action":
            tool_name = data["tool"]
            tool_args = data["args"]
            args_str = json.dumps(tool_args, ensure_ascii=False)
            print(f"[行动 #{i}] {tool_name}({args_str})")
            # 保存行动到执行轨迹
            await db_manager.save_trace(
                trace_id=f"trace-{run_id}-{seq}",
                run_id=run_id,
                iteration=i,
                trace_type="action",
                data={"tool": tool_name, "args": tool_args},
            )

        elif t == "observation":
            obs = data
            status = obs.get("status", "?")
            result = obs.get("result", "")
            if isinstance(result, str) and len(result) > 200:
                result = result[:200] + "..."
            print(f"[观察 #{i}] {status}: {result}")
            # 保存观察到执行轨迹
            await db_manager.save_trace(
                trace_id=f"trace-{run_id}-{seq}",
                run_id=run_id,
                iteration=i,
                trace_type="observation",
                data={
                    "tool_name": obs.get("tool_name", ""),
                    "tool_args": obs.get("tool_args", {}),
                    "result": obs.get("result", ""),
                    "status": obs.get("status", ""),
                },
            )

        elif t == "answer":
            answer = data["answer"]
            assistant_content = answer
            print(f"\n{'='*60}")
            print(f"答案: {answer}")
            print(f"{'='*60}\n")
            # 保存答案到执行轨迹
            await db_manager.save_trace(
                trace_id=f"trace-{run_id}-{seq}",
                run_id=run_id,
                iteration=i,
                trace_type="answer",
                data={"answer": answer},
            )

    # ---- 保存助手回复 ----
    if assistant_content:
        await db_manager.save_message(conversation_id, "assistant", assistant_content)

    # ---- 更新 Conversation 和 Run 状态 ----
    await db_manager.update_conversation(conversation_id, status="finished")
    await db_manager.update_run(run_id, status="completed", current_iteration=i if 'i' in dir() else 0)

    print(f"💾 已保存到 Conversation: {conversation_id}")
    print(f"💡 下次继续请使用: python -m src.main --session {conversation_id} \"新任务\"")


async def _show_history(db_manager: DatabaseManager) -> None:
    """打印所有历史 Conversation。"""
    conversations = await db_manager.list_conversations()
    if not conversations:
        print("📭 没有历史 Conversation。")
        return

    print(f"\n{'='*60}")
    print(f"📋 历史 Conversation 列表（共 {len(conversations)} 个）")
    print(f"{'='*60}\n")

    for conversation in conversations:
        msg_count = len(await db_manager.get_messages(conversation["id"]))
        print(f"  ID:     {conversation['id']}")
        print(f"  标题:   {conversation['title'] or '(无)'}")
        print(f"  状态:   {conversation['status']}")
        print(f"  消息数: {msg_count}")
        print(f"  更新:   {conversation['updated_at']}")
        print(f"  {'─'*40}")


# ======================================================================
# CLI 入口
# ======================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="IntelliAgent — AI 编程助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "读取 pyproject.toml 告诉我项目名"
  %(prog)s --resume "继续刚才的工作"
  %(prog)s --session conv-123456 "新任务"
  %(prog)s --history
        """,
    )
    parser.add_argument("task", nargs="*", help="任务描述")
    parser.add_argument("--resume", "-r", action="store_true", help="继续最近一次 Conversation")
    parser.add_argument("--session", "-s", type=str, help="指定 Conversation ID 继续（兼容参数）")
    parser.add_argument("--history", "-l", action="store_true", help="列出所有历史 Conversation")

    args = parser.parse_args()

    # 处理 task 参数（支持直接从位置参数读取）
    if args.task:
        task_text = " ".join(args.task)
    else:
        task_text = ""

    # 检查必须有任务或 --history
    if not task_text and not args.history:
        parser.print_help()
        print("\n❌ 请提供任务描述，或使用 --history 查看历史 Conversation。")
        sys.exit(1)

    asyncio.run(main(
        task=task_text,
        session_id=args.session,
        resume=args.resume,
        list_history=args.history,
    ))

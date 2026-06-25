"""CLI 应用层 — 管理 Runtime 生命周期和 REPL 循环。"""

from __future__ import annotations

from collections.abc import Callable

from src.cli.presenter import format_conversation_header, format_event, show_history, show_save_info
from src.runtime import AgentRuntime

_PROMPT = "\n> "


class CliApplication:
    """命令行应用门面，让 main.py 只负责启动。"""

    def __init__(self, runtime_factory: Callable[[], AgentRuntime] = AgentRuntime) -> None:
        self._runtime_factory = runtime_factory

    async def run(
        self,
        session_id: str | None = None,
        resume: bool = False,
        list_history: bool = False,
    ) -> None:
        runtime = self._runtime_factory()
        await runtime.initialize()

        if list_history:
            conversations = await runtime.list_conversations()
            await show_history(conversations, runtime.get_message_count)
            await runtime.shutdown()
            return

        conversation_id = await runtime.setup_conversation(task="", session_id=session_id, resume=resume)
        for warning in runtime.warnings:
            print(f"⚠️  {warning}")

        history_count = await runtime.get_message_count(conversation_id)
        format_conversation_header(history_count, conversation_id, runtime.is_new)

        await self._repl_loop(runtime)
        await runtime.shutdown()
        show_save_info(conversation_id)

    async def _repl_loop(self, runtime: AgentRuntime) -> None:
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
                self._show_help()
                continue

            await self._run_single_turn(runtime, user_input)

    async def _run_single_turn(self, runtime: AgentRuntime, user_input: str) -> str | None:
        assistant_content = ""
        async for event in runtime.execute(user_input):
            format_event(event)
            if event["type"] == "answer":
                assistant_content = event["data"]["answer"]

        return assistant_content if assistant_content else None

    def _show_help(self) -> None:
        print("命令：")
        print("  /exit  — 退出对话")
        print("  /help  — 显示此帮助")
        print("  直接输入任务描述即可与 AI 对话")


__all__ = ["CliApplication"]

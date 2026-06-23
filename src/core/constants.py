from __future__ import annotations

from typing import Any

DEFAULT_SYSTEM_PROMPT = """你是一个代码开发助手。"""

DEFAULT_AGENT_PROMPT = """你的任务是理解用户需求，使用可用工具完成任务。

核心原则：
1. 先分析需求，制定计划（使用 task_write 工具列出步骤），再逐步执行
2. 每次只调用一个工具，观察结果后再决定下一步
3. 遇到错误时分析原因，调整策略后重试
4. 保持代码简洁、可读、符合 Python 编码规范
5. 完成任务后直接回复最终结果，不要调用工具"""

DEFAULT_TOOLS_INSTRUCTION = """可用工具通过 function calling 机制提供，请根据任务需要选择合适的工具。"""


def build_history_context(
    history_messages: list[dict[str, Any]],
    max_messages: int = 20,
    max_content_length: int = 500,
) -> str | None:
    """将数据库中的历史消息构建为上下文字符串。"""
    if not history_messages:
        return None

    recent = history_messages[-max_messages:]

    lines = ["以下是之前的对话历史（供参考上下文）：", "---"]
    for msg in recent:
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."
        lines.append(f"[{role}] {content}")
    lines.append("---")

    return "\n".join(lines)


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_AGENT_PROMPT",
    "DEFAULT_TOOLS_INSTRUCTION",
    "build_history_context",
]

#!/usr/bin/env python3
"""
Token 估算模块 — 粗略估算消息列表的 token 数量。

仅用于预判是否接近上下文窗口上限，实际 token 数以 API 返回的 usage 为准。
"""

from __future__ import annotations

from typing import Any

# 粗略估算：中英文混编约 1 token ≈ 1.3 字符（中文约 1 token/字符，英文约 1 token/4字符）
TOKEN_PER_CHAR = 1.3
# 每条消息的开销（角色标记、格式等）
MESSAGE_OVERHEAD_TOKENS = 4
# 工具调用相关额外开销
TOOL_CALL_OVERHEAD_TOKENS = 10


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """粗略估算消息列表的 token 总数。

    仅用于预判是否接近上下文窗口上限，实际 token 数以 API 返回的 usage 为准。
    估算公式：每条消息开销 4 tokens + 内容字符数 × 1.3 + 工具调用开销。

    Args:
        messages: 消息列表

    Returns:
        估算的 token 总数
    """
    total = 0
    for msg in messages:
        total += MESSAGE_OVERHEAD_TOKENS
        content = msg.get("content", "")
        if content:
            total += int(len(str(content)) * TOKEN_PER_CHAR)
        if "tool_calls" in msg:
            total += TOOL_CALL_OVERHEAD_TOKENS * len(msg["tool_calls"])
    return total

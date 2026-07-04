from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ContextSummary:
    content: str
    source_message_count: int
    compression_count: int


def _summarize_messages(messages: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    current_task = ""

    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        if not content:
            tool_calls = m.get("tool_calls")
            if tool_calls:
                calls = ", ".join(tc.get("function", {}).get("name", "?") for tc in tool_calls)
                lines.append(f"助手调用工具: {calls}")
            continue

        if role == "user":
            current_task = content[:200]
            lines.append(f"用户目标: {current_task}")
        elif role == "assistant":
            truncated = content[:300]
            lines.append(f"助手回复: {truncated}")
        elif role == "tool":
            truncated = content[:200]
            lines.append(f"工具结果: {truncated}")

    if not lines:
        lines.append("(空对话)")

    summary = "\n".join(lines)
    if len(summary) > 2000:
        summary = summary[:2000] + "\n...(截断)"

    return f"以下是已压缩的上下文摘要：\n{summary}"


class ContextManager:
    def __init__(self, max_context_tokens: int, compact_threshold: float = 0.75) -> None:
        self._max_context_tokens = max_context_tokens
        self._compact_threshold = compact_threshold

        self._instructions: list[dict[str, Any]] = []
        self._messages: list[dict[str, Any]] = []
        self._summary: ContextSummary | None = None

    def initialize_instructions(self, system_prompt: str, agent_prompt: str, tools_instruction: str) -> None:
        self._instructions = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": agent_prompt},
            {"role": "system", "content": tools_instruction},
        ]

    def add_user_message(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str | None = None, tool_calls: list[dict[str, Any]] | None = None) -> None:
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._messages.append(msg)

    def add_tool_message(self, tool_call_id: str, content: str) -> None:
        self._messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})

    def load_history(self, messages: list[dict[str, Any]]) -> None:
        self._messages = [dict(m) for m in messages]

    def compact_if_needed(self, estimated_tokens: int) -> ContextSummary | None:
        threshold = int(self._max_context_tokens * self._compact_threshold)
        if estimated_tokens < threshold:
            return None

        return self._compact_to_summary()

    def _compact_to_summary(self) -> ContextSummary:
        content = _summarize_messages(self._messages)
        source_count = len(self._messages)

        compression_count = 1
        if self._summary is not None:
            compression_count = self._summary.compression_count + 1
            content = _summarize_messages(
                [{"role": "assistant", "content": self._summary.content}] + self._messages[-2:]
            )

        self._summary = ContextSummary(
            content=content,
            source_message_count=source_count,
            compression_count=compression_count,
        )
        self._messages = []

        return self._summary

    def get_messages(self) -> list[dict[str, Any]]:
        result = list(self._instructions)

        if self._summary is not None:
            result.append({"role": "user", "content": self._summary.content})

        for m in self._messages:
            # Always include recent messages on top of summary
            result.append(dict(m))

        return result

    @property
    def summary(self) -> ContextSummary | None:
        return self._summary


__all__ = ["ContextManager", "ContextSummary"]

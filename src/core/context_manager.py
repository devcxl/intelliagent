from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class ContextSummary:
    content: str
    source_message_count: int
    compression_count: int


def _summarize_messages(messages: list[dict[str, Any]]) -> str:
    """按 ADR 0001 生成结构化摘要。

    从消息列表中提取当前目标、已完成动作、关键观察、涉及文件，
    输出结构化文本而非简单截断。
    """
    goals: list[str] = []
    actions: list[str] = []
    observations: list[str] = []
    files: set[str] = set()

    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "") or ""
        tool_calls = m.get("tool_calls")

        if role == "user":
            goals.append(content[:200])
        elif role == "assistant":
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "?")
                    actions.append(f"调用工具 {name}")
                    args_raw = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                        for key in ("path", "file", "filename"):
                            if key in args and isinstance(args[key], str):
                                files.add(args[key])
                    except (json.JSONDecodeError, TypeError):
                        pass
            if content:
                actions.append(content[:200])
        elif role == "tool":
            observations.append(content[:200])

    sections: list[str] = ["以下是已压缩的上下文摘要："]

    if goals:
        sections.append("\n当前目标:")
        for g in goals[-3:]:
            sections.append(f"- {g}")

    if actions:
        sections.append("\n已完成动作:")
        for a in actions[-10:]:
            sections.append(f"- {a}")

    if observations:
        sections.append("\n关键观察:")
        for o in observations[-5:]:
            sections.append(f"- {o}")

    if files:
        sections.append("\n涉及文件:")
        for f in sorted(files):
            sections.append(f"- {f}")

    sections.append("\n下一步建议:")
    sections.append("- 继续执行未完成的任务")

    summary = "\n".join(sections)
    if len(summary) > 2000:
        summary = summary[:2000] + "\n...(截断)"

    return summary


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

    def reset(self) -> None:
        """清空消息和摘要，保留 instructions。用于重新开始一轮对话。"""
        self._messages = []
        self._summary = None

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

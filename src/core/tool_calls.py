"""ToolCallDelta 增量归并：把流式参数片段拼成模型侧 tool_calls 形态。"""

from __future__ import annotations

from typing import Any

from src.llm.stream import ToolCallDelta


class ToolCallBuilder:
    """把 ToolCallDelta 增量按 index 归并成完整 tool call（id/name 只在首个增量出现，参数逐段拼接）。"""

    def __init__(self) -> None:
        self._calls: dict[int, dict[str, str]] = {}

    def add(self, delta: ToolCallDelta) -> None:
        call = self._calls.setdefault(delta.index, {"id": "", "name": "", "arguments": ""})
        call["id"] = call["id"] or (delta.id or "")
        call["name"] = call["name"] or (delta.name or "")
        call["arguments"] += delta.arguments_delta

    def build(self) -> list[dict[str, Any]]:
        """按 index 顺序产出模型侧 tool_calls 形态；缺失 id 时按 index 兜底生成。"""
        return [
            {
                "id": call["id"] or f"call_{index}",
                "type": "function",
                "function": {"name": call["name"], "arguments": call["arguments"]},
            }
            for index, call in sorted(self._calls.items())
        ]

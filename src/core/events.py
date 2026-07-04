from __future__ import annotations

from typing import Any


def answer_event(
    step: int, content: str | None, total_tokens: int, prompt_tokens: int, completion_tokens: int, cached_tokens: int
) -> dict[str, Any]:
    return {
        "type": "answer",
        "iteration": step,
        "data": {
            "answer": content or "",
            "num_turns": step,
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_tokens": cached_tokens,
        },
    }


def thought_event(step: int, content: str | None, tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "type": "thought",
        "iteration": step,
        "data": {"content": content, "has_tool_calls": True, "tool_calls": tool_calls},
    }


def action_event(step: int, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
    return {"type": "action", "iteration": step, "data": {"tool": tool_name, "args": tool_args}}


def observation_event(
    step: int,
    tool_call_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    result: str,
) -> dict[str, Any]:
    return {
        "type": "observation",
        "iteration": step,
        "data": {
            "iteration": step,
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "result": result,
            "status": "success",
            "error": None,
            "execution_time": 0,
        },
    }


__all__ = ["answer_event", "thought_event", "action_event", "observation_event"]

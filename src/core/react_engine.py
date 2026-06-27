from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol

from src.core.constants import DEFAULT_SYSTEM_PROMPT
from src.permission import (
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)
from src.skills.registry import SkillRegistry
from src.tools.registry import NoopToolRegistry
from src.types.llm import LLMClientProtocol
from src.utils.logger import logger

_RECENT_CONTEXT_MESSAGES = 6
_COMPACT_TOKEN_REDUCTION_RATIO = 0.5


class ToolRegistryProtocol(Protocol):
    """ReactEngine 只依赖工具注册表能力，不依赖 tools 包的具体全局实例。"""

    def get_openai_tools(self) -> list[dict[str, Any]]: ...

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str: ...


def _to_tool_call_list(raw: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": tc.id,
            "type": "function",
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            },
        }
        for tc in raw
    ]


@dataclass
class _TokenUsage:
    prompt: int = 0
    completion: int = 0
    cached: int = 0

    def record(self, response: Any) -> int:
        usage = getattr(response, "usage", None)
        if not usage:
            return 0

        total = getattr(usage, "total_tokens", 0) or 0
        self.prompt += getattr(usage, "prompt_tokens", 0) or 0
        self.completion += getattr(usage, "completion_tokens", 0) or 0

        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
        if cached:
            self.cached += cached
        return total


class ReactEngine:
    def __init__(
        self,
        llm_client: LLMClientProtocol,
        tools_registry: ToolRegistryProtocol | None = None,
        permission_engine: PermissionEngineProtocol | None = None,
        permission_callback: PermissionCallbackProtocol | None = None,
        context_limit: int | None = None,
        skill_registry: SkillRegistry | None = None,
        compact_callback: Callable[[list[str], str], Awaitable[None]] | None = None,
    ):
        self.llm_client = llm_client
        self._registry = tools_registry if tools_registry is not None else NoopToolRegistry()
        self._permission_engine = permission_engine
        self._permission_callback = permission_callback
        self._skill_registry = skill_registry
        self._compact_callback = compact_callback

        self.max_context_tokens = context_limit or 128_000

        self.messages: list[dict[str, Any]] = []
        self.total_tokens = 0

    # ------------------------------------------------------------------
    # 消息操作
    # ------------------------------------------------------------------

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str | None = None, tool_calls: list[dict[str, Any]] | None = None):
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_message(self, tool_call_id: str, content: str):
        self.messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})

    def load_history(self, messages: list[dict[str, Any]]) -> None:
        """从持久化消息列表加载历史，前置 system message。

        Args:
            messages: DB 中已存储的对话消息（role + content）
        """
        self.messages = [self._build_system_message(), *(dict(message) for message in messages)]

    def _build_system_message(self) -> dict[str, Any]:
        """构建 system message，注入 available_skills（如有）。"""
        content = DEFAULT_SYSTEM_PROMPT
        if self._skill_registry and self._skill_registry.list_names():
            xml = self._skill_registry.generate_available_skills_xml()
            content += "\n\n" + xml + "\n\n当任务匹配某个 skill 的描述时，使用 skill 工具加载其完整指令。"
        return {"role": "system", "content": content}

    def _check_token_limit(self) -> bool:
        return self.total_tokens >= self.max_context_tokens

    # ------------------------------------------------------------------
    # 上下文压缩
    # ------------------------------------------------------------------

    async def compact_context(self):
        if self.total_tokens < self.max_context_tokens:
            return

        system = self.messages[0] if self.messages and self.messages[0]["role"] == "system" else None
        kept = [system] if system else []

        recent = (
            self.messages[-_RECENT_CONTEXT_MESSAGES:]
            if len(self.messages) > _RECENT_CONTEXT_MESSAGES
            else self.messages[-len(self.messages) :]
        )
        middle = self.messages[len(kept) : -len(recent)] if len(self.messages) > len(kept) + len(recent) else []

        if middle:
            prompt = "请将以下对话压缩为一段简洁的中文摘要：\n\n" + json.dumps(middle, ensure_ascii=False)
            resp = await self.llm_client.chat_async(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            summary = getattr(resp, "content", "") or ""

            msg_ids = [m["_msg_id"] for m in middle if "_msg_id" in m]
            if msg_ids and self._compact_callback:
                await self._compact_callback(msg_ids, summary)

            kept.append({"role": "system", "content": f"以下是被压缩的上下文摘要：{summary}"})

        kept.extend(recent)
        self.messages = kept
        self.total_tokens = int(self.total_tokens * _COMPACT_TOKEN_REDUCTION_RATIO)

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_call: dict[str, Any]) -> str:
        tool_name = tool_call.get("function", {}).get("name", "")
        args_raw = tool_call.get("function", {}).get("arguments", "{}")

        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            args = {}

        if self._permission_engine:
            # 权限检查必须发生在 ToolRegistry.call_tool 之前，确保副作用工具不会先执行。
            decision = self._permission_engine.check(tool_name, args)
            if decision.action == "deny":
                return json.dumps({"status": "error", "error": f"权限拒绝: {decision.reason}"}, ensure_ascii=False)
            if decision.action == "ask":
                if self._permission_callback:
                    approved = await self._permission_callback.on_prompt(tool_name, args, decision.reason)
                    if not approved:
                        return json.dumps({"status": "error", "error": "用户拒绝执行"}, ensure_ascii=False)
                else:
                    return json.dumps(
                        {"status": "error", "error": f"需要确认但无回调: {decision.reason}"},
                        ensure_ascii=False,
                    )

        result = await self._registry.call_tool(tool_name=tool_name, **args)

        return result

    # ------------------------------------------------------------------
    # _loop — 核心循环（事件流）
    # ------------------------------------------------------------------

    async def _loop(self) -> AsyncGenerator[dict[str, Any], None]:
        usage = _TokenUsage()
        step = 0

        while True:
            step += 1
            logger.debug(f"ReactEngine - 第 {step} 轮 | tokens={self.total_tokens}")

            await self._maybe_compact_context()
            response = await self._call_llm()
            self.total_tokens += usage.record(response)

            content, tool_calls = self._extract_response(response)

            self.add_assistant_message(content=content, tool_calls=tool_calls)

            if not tool_calls:
                logger.info(f"Agent 完成 | turns={step} tokens={self.total_tokens}")
                yield self._answer_event(step, content, usage)
                return

            yield self._thought_event(step, content, tool_calls)
            async for event in self._execute_tool_calls(tool_calls, step):
                yield event

    async def _maybe_compact_context(self) -> None:
        if self._check_token_limit():
            await self.compact_context()

    async def _call_llm(self) -> Any:
        clean = [{k: v for k, v in m.items() if not k.startswith("_")} for m in self.messages]
        return await self.llm_client.chat_async(
            messages=clean,
            temperature=0.3,
            tools=self._registry.get_openai_tools(),
        )

    def _extract_response(self, response: Any) -> tuple[str | None, list[dict[str, Any]] | None]:
        content = getattr(response, "content", None)
        raw_tool_calls = getattr(response, "tool_calls", None)
        tool_calls = _to_tool_call_list(raw_tool_calls) if raw_tool_calls else None
        return content, tool_calls

    def _answer_event(self, step: int, content: str | None, usage: _TokenUsage) -> dict[str, Any]:
        return {
            "type": "answer",
            "iteration": step,
            "data": {
                "answer": content or "",
                "num_turns": step,
                "total_tokens": self.total_tokens,
                "prompt_tokens": usage.prompt,
                "completion_tokens": usage.completion,
                "cached_tokens": usage.cached,
            },
        }

    def _thought_event(
        self, step: int, content: str | None, tool_calls: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        return {
            "type": "thought",
            "iteration": step,
            "data": {"content": content, "has_tool_calls": True, "tool_calls": tool_calls},
        }

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        step: int,
    ) -> AsyncGenerator[dict[str, Any], None]:
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = self._parse_tool_args(tool_call)

            yield {"type": "action", "iteration": step, "data": {"tool": tool_name, "args": tool_args}}

            result = await self.execute_tool(tool_call)
            self.add_tool_message(tool_call["id"], result)

            yield {
                "type": "observation",
                "iteration": step,
                "data": {
                    "iteration": step,
                    "tool_call_id": tool_call["id"],
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "result": result,
                    "status": "success",
                    "error": None,
                    "execution_time": 0,
                },
            }

    def _parse_tool_args(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        tool_args_raw = tool_call["function"]["arguments"]
        try:
            return json.loads(tool_args_raw) if isinstance(tool_args_raw, str) else tool_args_raw
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------------
    # run — 主入口
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
    ) -> dict[str, Any]:
        if not self.messages:
            self.messages = [self._build_system_message()]
        self.add_user_message(task)

        async for event in self._loop():
            if event["type"] == "answer":
                data = event["data"]
                return {
                    "success": True,
                    "answer": data["answer"],
                    "num_turns": data["num_turns"],
                    "total_tokens": data["total_tokens"],
                    "prompt_tokens": data["prompt_tokens"],
                    "completion_tokens": data["completion_tokens"],
                    "cached_tokens": data["cached_tokens"],
                }

        return {"success": False, "answer": ""}

    # ------------------------------------------------------------------
    # iter_steps — 流式事件生成
    # ------------------------------------------------------------------

    async def iter_steps(
        self,
        task: str,
        reset_state: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if reset_state or not self.messages:
            self.messages = [self._build_system_message()]
        self.add_user_message(task)

        async for event in self._loop():
            yield event


__all__ = ["ReactEngine"]

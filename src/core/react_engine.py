from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from src.core.constants import DEFAULT_SYSTEM_PROMPT
from src.permission import (
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)
from src.skills.registry import SkillRegistry
from src.tools.registry import _default_registry
from src.types.llm import LLMClientProtocol
from src.types.memory import MemoryProtocol
from src.utils.logger import logger

MAX_STEPS = 50


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


class ReactEngine:
    def __init__(
        self,
        llm_client: LLMClientProtocol,
        tools_registry: Any = None,
        memory: MemoryProtocol | None = None,
        permission_engine: PermissionEngineProtocol | None = None,
        permission_callback: PermissionCallbackProtocol | None = None,
        context_limit: int | None = None,
        max_steps: int = MAX_STEPS,
        skill_registry: SkillRegistry | None = None,
    ):
        self.llm_client = llm_client
        self._registry = tools_registry if tools_registry is not None else _default_registry
        self.memory = memory
        self._permission_engine = permission_engine
        self._permission_callback = permission_callback
        self._skill_registry = skill_registry

        self.max_context_tokens = context_limit or 128_000
        self.max_steps = max_steps

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

        recent = self.messages[-6:] if len(self.messages) > 6 else self.messages[-len(self.messages) :]
        middle = self.messages[len(kept) : -len(recent)] if len(self.messages) > len(kept) + len(recent) else []

        if middle:
            prompt = "请将以下对话压缩为一段简洁的中文摘要：\n\n" + json.dumps(middle, ensure_ascii=False)
            resp = await self.llm_client.chat_async(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            summary = getattr(resp, "content", "") or ""
            kept.append({"role": "user", "content": f"以下是被压缩的上下文摘要：{summary}"})

        kept.extend(recent)
        self.messages = kept
        self.total_tokens = int(self.total_tokens * 0.5)

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_call: dict[str, Any]) -> str:
        name = tool_call.get("function", {}).get("name", "")
        args_raw = tool_call.get("function", {}).get("arguments", "{}")

        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            args = {}

        if self._permission_engine:
            decision = self._permission_engine.check(name, args)
            if decision.action == "deny":
                return json.dumps({"status": "error", "error": f"权限拒绝: {decision.reason}"}, ensure_ascii=False)
            if decision.action == "ask":
                if self._permission_callback:
                    approved = await self._permission_callback.on_prompt(name, args, decision.reason)
                    if not approved:
                        return json.dumps({"status": "error", "error": "用户拒绝执行"}, ensure_ascii=False)
                else:
                    return json.dumps(
                        {"status": "error", "error": f"需要确认但无回调: {decision.reason}"},
                        ensure_ascii=False,
                    )

        fn = self._registry.get_tool_fn(name)
        if fn is None:
            return json.dumps({"status": "error", "error": f"未知工具: {name}"}, ensure_ascii=False)

        try:
            result = await fn(**args)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)

        if self.memory:
            self.memory.add_observation({"tool_name": name, "tool_args": args, "result": result})

        return result

    # ------------------------------------------------------------------
    # _loop — 核心循环
    # ------------------------------------------------------------------

    async def _loop(self, step_limit: int) -> dict[str, Any]:
        total_prompt = 0
        total_completion = 0
        total_cached = 0

        for step in range(1, step_limit + 1):
            logger.debug(f"ReactEngine - 第 {step} 轮 | tokens={self.total_tokens}")

            if self._check_token_limit():
                await self.compact_context()

            response = await self.llm_client.chat_async(
                messages=self.messages,
                temperature=0.3,
                tools=self._registry.get_openai_tools(),
            )

            usage = getattr(response, "usage", None)
            if usage:
                self.total_tokens += getattr(usage, "total_tokens", 0) or 0
                total_prompt += getattr(usage, "prompt_tokens", 0) or 0
                total_completion += getattr(usage, "completion_tokens", 0) or 0
                details = getattr(usage, "prompt_tokens_details", None)
                cached = getattr(details, "cached_tokens", 0) if details else 0
                if cached:
                    total_cached += cached

            content = getattr(response, "content", None)
            raw_tc = getattr(response, "tool_calls", None)
            tool_calls = _to_tool_call_list(raw_tc) if raw_tc else None

            self.add_assistant_message(content=content, tool_calls=tool_calls)

            if not tool_calls:
                logger.info(f"Agent 完成 | turns={step} tokens={self.total_tokens}")
                return {
                    "success": True,
                    "answer": content or "",
                    "num_turns": step,
                    "total_tokens": self.total_tokens,
                    "prompt_tokens": total_prompt,
                    "completion_tokens": total_completion,
                    "cached_tokens": total_cached,
                }

            for tc in tool_calls:
                result = await self.execute_tool(tc)
                self.add_tool_message(tc["id"], result)

        logger.warning(f"安全网触发 | max_steps={step_limit}")
        return {
            "success": False,
            "answer": "",
            "num_turns": step_limit,
            "total_tokens": self.total_tokens,
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "cached_tokens": total_cached,
            "summary": "安全网触发：达到最大步数",
        }

    # ------------------------------------------------------------------
    # run — 主入口
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
        max_steps: int | None = None,
        history_context: str | None = None,
    ) -> dict[str, Any]:
        self.messages = [self._build_system_message()]

        user_content = task
        if history_context:
            user_content = f"{history_context}\n\n{task}"
        self.add_user_message(user_content)

        return await self._loop(max_steps or self.max_steps)

    # ------------------------------------------------------------------
    # iter_steps — 流式事件生成
    # ------------------------------------------------------------------

    async def iter_steps(
        self,
        task: str,
        history_context: str | None = None,
        max_steps: int | None = None,
        start_iteration: int = 1,
        reset_state: bool = True,
        seed_observations: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if reset_state:
            self.messages = [self._build_system_message()]

        user_content = task
        if history_context:
            user_content = f"{history_context}\n\n{task}"
        self.add_user_message(user_content)

        step_limit = max_steps or self.max_steps

        for step in range(start_iteration, step_limit + 1):
            if self._check_token_limit():
                await self.compact_context()

            response = await self.llm_client.chat_async(
                messages=self.messages,
                temperature=0.3,
                tools=self._registry.get_openai_tools(),
            )

            usage = getattr(response, "usage", None)
            if usage:
                self.total_tokens += getattr(usage, "total_tokens", 0) or 0

            content = getattr(response, "content", None)
            raw_tc = getattr(response, "tool_calls", None)
            tool_calls = _to_tool_call_list(raw_tc) if raw_tc else None

            self.add_assistant_message(content=content, tool_calls=tool_calls)

            yield {
                "type": "thought",
                "iteration": step,
                "data": {"content": content, "has_tool_calls": bool(tool_calls)},
            }

            if not tool_calls:
                yield {
                    "type": "answer",
                    "iteration": step,
                    "data": {"answer": content or ""},
                }
                return

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                tool_args_str = tc["function"]["arguments"]
                try:
                    tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                except json.JSONDecodeError:
                    tool_args = {}

                yield {
                    "type": "action",
                    "iteration": step,
                    "data": {"tool": tool_name, "args": tool_args},
                }

                result = await self.execute_tool(tc)
                self.add_tool_message(tc["id"], result)

                yield {
                    "type": "observation",
                    "iteration": step,
                    "data": {
                        "iteration": step,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "result": result,
                        "status": "success",
                        "error": None,
                        "execution_time": 0,
                    },
                }

        yield {
            "type": "answer",
            "iteration": step_limit,
            "data": {"answer": "安全网触发"},
        }


__all__ = ["ReactEngine"]

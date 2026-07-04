from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Protocol

from src.core.constants import DEFAULT_SYSTEM_PROMPT
from src.core.context_manager import ContextManager
from src.core.events import action_event, answer_event, observation_event, thought_event
from src.core.tool_executor import ToolExecutor
from src.permission import (
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)
from src.skills.registry import SkillRegistry
from src.tools.registry import NoopToolRegistry
from src.types.llm import LLMClientProtocol
from src.utils.logger import logger


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
        self._context_manager = ContextManager(max_context_tokens=self.max_context_tokens)
        self._tool_executor = ToolExecutor(
            registry=self._registry,
            permission_engine=self._permission_engine,
            permission_callback=self._permission_callback,
        )

        self.messages: list[dict[str, Any]] = []
        self.total_tokens = 0

    # ------------------------------------------------------------------
    # 消息操作
    # ------------------------------------------------------------------

    def add_user_message(self, content: str):
        self.messages.append({"role": "user", "content": content})
        self._context_manager.add_user_message(content)

    def add_assistant_message(self, content: str | None = None, tool_calls: list[dict[str, Any]] | None = None):
        msg: dict[str, Any] = {"role": "assistant", "content": content or ""}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)
        self._context_manager.add_assistant_message(content=content, tool_calls=tool_calls)

    def add_tool_message(self, tool_call_id: str, content: str):
        self.messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})
        self._context_manager.add_tool_message(tool_call_id, content)

    def load_history(self, messages: list[dict[str, Any]]) -> None:
        self._context_manager.load_history(messages)
        self.messages = [self._build_system_message(), *(dict(message) for message in messages)]

    def _build_system_message(self) -> dict[str, Any]:
        content = DEFAULT_SYSTEM_PROMPT
        if self._skill_registry and self._skill_registry.list_names():
            xml = self._skill_registry.generate_available_skills_xml()
            content += "\n\n" + xml + "\n\n当任务匹配某个 skill 的描述时，使用 skill 工具加载其完整指令。"
        return {"role": "system", "content": content}

    # ------------------------------------------------------------------
    # 上下文压缩
    # ------------------------------------------------------------------

    async def _maybe_compact_context(self) -> None:
        summary = self._context_manager.compact_if_needed(estimated_tokens=self.total_tokens)
        if summary is None:
            return

        self.messages = [self._build_system_message(), {"role": "user", "content": summary.content}]
        self.total_tokens = int(self.total_tokens * 0.5)

        if self._compact_callback:
            await self._compact_callback([], summary.content)

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_call: dict[str, Any]) -> str:
        result = await self._tool_executor.execute(tool_call)
        return result.content

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
                yield answer_event(step, content, self.total_tokens, usage.prompt, usage.completion, usage.cached)
                return

            yield thought_event(step, content, tool_calls)
            async for event in self._execute_tool_calls(tool_calls, step):
                yield event

    async def _call_llm(self) -> Any:
        context = self._context_manager.get_messages()
        clean = [{k: v for k, v in m.items() if not k.startswith("_")} for m in context]
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

    async def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        step: int,
    ) -> AsyncGenerator[dict[str, Any], None]:
        for tool_call in tool_calls:
            result = await self._tool_executor.execute(tool_call)
            yield action_event(step, result.tool_name, result.tool_args)
            self.add_tool_message(result.tool_call_id, result.content)
            yield observation_event(step, result.tool_call_id, result.tool_name, result.tool_args, result.content)

    # ------------------------------------------------------------------
    # run — 主入口
    # ------------------------------------------------------------------

    async def run(
        self,
        task: str,
    ) -> dict[str, Any]:
        if not self.messages:
            self.messages = [self._build_system_message()]
            self._context_manager.initialize_instructions(
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                agent_prompt="",
                tools_instruction="",
            )
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
            self._context_manager.initialize_instructions(
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                agent_prompt="",
                tools_instruction="",
            )
        self.add_user_message(task)

        async for event in self._loop():
            yield event


__all__ = ["ReactEngine"]

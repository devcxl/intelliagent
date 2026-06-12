from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from src.tools.registry import _default_registry
from src.core.context_manager import ContextManager, DEFAULT_SYSTEM_PROMPT
from src.types.permission import (
    LLMClientProtocol,
    MemoryProtocol,
    PermissionEngineProtocol,
    PermissionCallbackProtocol,
)
from src.utils.logger import logger


SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT


class ReactEngine:
    """ReAct 循环引擎 — 对齐 Claude Code 设计。"""

    DEFAULT_MAX_TOKENS = 128_000
    TOKEN_WARN_RATIO = 0.8
    DEFAULT_MAX_CONSECUTIVE_REPEATS = 5
    REPEAT_WARN_THRESHOLD = 3

    def __init__(
        self,
        llm_client: LLMClientProtocol,
        tools_registry: Any = None,
        memory: MemoryProtocol | None = None,
        context: Any = None,
        context_manager: ContextManager | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_iterations: int | None = None,
        max_consecutive_repeats: int = DEFAULT_MAX_CONSECUTIVE_REPEATS,
        permission_engine: PermissionEngineProtocol | None = None,
        permission_callback: PermissionCallbackProtocol | None = None,
    ):
        self.llm_client = llm_client
        self._registry = tools_registry if tools_registry is not None else _default_registry
        self.memory = memory
        self.context = context
        self.max_tokens = max_tokens
        self.max_iterations = max_iterations
        self.max_consecutive_repeats = max_consecutive_repeats
        self._permission_engine = permission_engine
        self._permission_callback = permission_callback
        self._ctx = context_manager or ContextManager(
            system_prompt=SYSTEM_PROMPT,
            max_tokens=max_tokens,
        )

    # =======================================================================
    # _loop() — 核心循环生成器，供 run() 和 iter_steps() 共用
    # =======================================================================
    async def _loop(
        self,
        task: str,
        history_context: str | None = None,
        *,
        token_limit: int | None = None,
        repeat_limit: int | None = None,
        iteration_limit: int | None = None,
        reset_state: bool = True,
    ) -> AsyncGenerator[tuple[Any, dict[str, Any]], None]:
        if reset_state:
            if self.memory:
                self.memory.clear_memory()
            if self.context:
                self.context.add_context(f"用户任务: {task}")

        if reset_state or not self._ctx.get_messages():
            self._ctx.initialize(task, history_context=history_context)

        tools = self._registry.get_openai_tools()
        tool_tokens_estimate = self._estimate_extra_tokens(tools)

        tok_limit = token_limit if token_limit is not None else self.max_tokens
        rep_limit = repeat_limit if repeat_limit is not None else self.max_consecutive_repeats
        iter_limit = iteration_limit if iteration_limit is not None else self.max_iterations

        logger.debug(
            f"ReactEngine - 循环开始 | task={task} token_limit={tok_limit} "
            f"repeat_limit={rep_limit} iteration_limit={iter_limit}"
        )

        num_turns = 0
        total_tokens = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        last_call: tuple[str, str] | None = None
        consecutive_repeats = 0

        while True:
            if iter_limit is not None and num_turns >= iter_limit:
                logger.debug(f"ReactEngine - 循环退出 | reason=max_iterations")
                logger.warning(f"安全网触发终止 | turns={num_turns} max_iterations={iter_limit}")
                state = {
                    "success": False, "answer": "",
                    "num_turns": num_turns,
                    "total_tokens": total_tokens,
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "cached_tokens": total_cached_tokens,
                    "summary": "安全网触发：达到最大轮数",
                }
                yield None, state
                return

            num_turns += 1
            logger.debug(f"ReactEngine - 第 {num_turns} 轮开始 | total_tokens={total_tokens}")

            safety = self._check_safety(total_tokens, consecutive_repeats, tok_limit, rep_limit)
            logger.debug(
                f"ReactEngine - 安全网检查 | result={safety} "
                f"tokens={total_tokens} repeats={consecutive_repeats}"
            )
            if safety == "stop":
                logger.debug(f"ReactEngine - 循环退出 | reason=safety_stop")
                logger.warning(f"安全网触发终止 | turns={num_turns} tokens={total_tokens}")
                state = {
                    "success": False, "answer": "",
                    "num_turns": num_turns,
                    "total_tokens": total_tokens,
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "cached_tokens": total_cached_tokens,
                    "summary": "安全网触发：任务终止",
                }
                yield None, state
                return
            elif safety == "warn":
                self._ctx.add_user_message("⚠️ 系统提醒：请尽快总结当前进展并完成任务。")

            logger.debug(
                f"ReactEngine - 压缩上下文前 | msg_count={len(self._ctx.get_messages())}"
            )
            compacted = self._ctx.compact_if_needed(
                max_tokens=tok_limit,
                extra_tokens=tool_tokens_estimate,
            )
            logger.debug(
                f"ReactEngine - 压缩上下文后 | compacted={compacted}"
            )

            logger.debug(
                f"ReactEngine - LLM 调用前 | msg_count={len(self._ctx.get_messages())} "
                f"token_estimate={self._ctx.estimate_tokens() + tool_tokens_estimate}"
            )
            response = await self.llm_client.chat_async(
                messages=self._ctx.get_messages(),
                temperature=0.3,
                tools=tools,
            )

            if hasattr(response, "usage") and response.usage:
                usage = response.usage
                total_tokens += getattr(usage, "total_tokens", 0) or 0
                total_prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                total_completion_tokens += getattr(usage, "completion_tokens", 0) or 0
                details = getattr(usage, "prompt_tokens_details", None)
                cached_tokens = getattr(details, "cached_tokens", 0) if details else 0
                if cached_tokens:
                    total_cached_tokens += cached_tokens

            logger.debug(
                f"ReactEngine - LLM 调用后 | "
                f"total_tokens={total_tokens} prompt_tokens={total_prompt_tokens} "
                f"completion_tokens={total_completion_tokens}"
            )

            if not response.tool_calls:
                logger.debug(f"ReactEngine - 循环退出 | reason=agent_finished")

            state = {
                "num_turns": num_turns,
                "total_tokens": total_tokens,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "cached_tokens": total_cached_tokens,
                "last_call": last_call,
                "consecutive_repeats": consecutive_repeats,
            }
            yield response, state

            if response.tool_calls:
                tool_calls_msg = self._format_tool_calls(response.tool_calls)
                self._ctx.add_assistant_message(response.content, tool_calls_msg)

                for tc in response.tool_calls:
                    tool_name = tc.function.name
                    tool_args_str = tc.function.arguments

                    current_call = (tool_name, tool_args_str)
                    if current_call == last_call:
                        consecutive_repeats += 1
                    else:
                        consecutive_repeats = 1
                    last_call = current_call

                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {}

                    logger.debug(
                        f"ReactEngine - 执行工具 | tool={tool_name} args_len={len(tool_args_str)}"
                    )
                    result = await self._execute_tool(tool_name, tool_args)
                    logger.debug(
                        f"ReactEngine - 工具结果 | tool={tool_name} result_len={len(result)}"
                    )
                    self._ctx.add_tool_message(tc.id, result)

                    if self.memory:
                        self.memory.add_observation({
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "result": result,
                        })
            else:
                return

    # =======================================================================
    # run() — 异步执行入口，返回最终结果字典
    # =======================================================================
    async def run(
        self,
        task: str,
        max_iterations: int | None = None,
        history_context: str | None = None,
    ) -> dict[str, Any]:
        async for response, state in self._loop(
            task,
            history_context=history_context,
            iteration_limit=max_iterations,
        ):
            if response is None:
                return state

            if not response.tool_calls:
                logger.info(f"Agent 完成 | turns={state['num_turns']} tokens={state['total_tokens']}")
                return {
                    "success": True,
                    "answer": response.content or "",
                    "num_turns": state["num_turns"],
                    "total_tokens": state["total_tokens"],
                    "prompt_tokens": state["prompt_tokens"],
                    "completion_tokens": state["completion_tokens"],
                    "cached_tokens": state["cached_tokens"],
                }

        return {"success": False, "answer": "", "num_turns": 0, "total_tokens": 0,
                "prompt_tokens": 0, "completion_tokens": 0, "cached_tokens": 0,
                "summary": "未知错误"}

    # =======================================================================
    # iter_steps() — 异步流式生成器，供 WebSocket 实时推送
    # =======================================================================
    async def iter_steps(
        self,
        task: str,
        history_context: str | None = None,
        max_tokens: int | None = None,
        max_consecutive_repeats: int | None = None,
        max_iterations: int | None = None,
        start_iteration: int = 1,
        reset_state: bool = True,
        seed_observations: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        repeat_limit = max_consecutive_repeats if max_consecutive_repeats is not None else self.max_consecutive_repeats

        async for response, state in self._loop(
            task,
            history_context=history_context,
            token_limit=token_limit,
            repeat_limit=repeat_limit,
            iteration_limit=max_iterations,
            reset_state=reset_state,
        ):
            if response is None:
                yield {
                    "type": "answer",
                    "iteration": state["num_turns"],
                    "data": {"answer": state.get("summary", "安全网触发")},
                }
                return

            yield {
                "type": "thought",
                "iteration": state["num_turns"],
                "data": {"content": response.content, "has_tool_calls": bool(response.tool_calls)},
            }

            if response.tool_calls:
                for tc in response.tool_calls:
                    tool_name = tc.function.name
                    tool_args_str = tc.function.arguments
                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {}

                    yield {
                        "type": "action",
                        "iteration": state["num_turns"],
                        "data": {"tool": tool_name, "args": tool_args},
                    }

                    result = await self._execute_tool(tool_name, tool_args)

                    obs = {
                        "iteration": state["num_turns"],
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "result": result,
                        "status": "success",
                        "error": None,
                        "execution_time": 0,
                    }
                    yield {
                        "type": "observation",
                        "iteration": state["num_turns"],
                        "data": obs,
                    }
            else:
                yield {
                    "type": "answer",
                    "iteration": state["num_turns"],
                    "data": {"answer": response.content or ""},
                }
                return

    # =======================================================================
    # _format_tool_calls() — 转换为 OpenAI messages 协议格式
    # =======================================================================
    @staticmethod
    def _format_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
        return [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]

    @staticmethod
    def _estimate_extra_tokens(value: Any) -> int:
        return int(len(json.dumps(value, ensure_ascii=False)) * 1.3)

    # =======================================================================
    # _check_safety() — 双层安全网
    # =======================================================================
    def _check_safety(
        self,
        total_tokens: int,
        consecutive_repeats: int,
        token_limit: int | None = None,
        repeat_limit: int | None = None,
    ) -> str:
        max_tok = token_limit if token_limit is not None else self.max_tokens
        max_rep = repeat_limit if repeat_limit is not None else self.max_consecutive_repeats

        if total_tokens >= max_tok:
            return "stop"
        if consecutive_repeats >= max_rep:
            return "stop"
        if total_tokens >= max_tok * self.TOKEN_WARN_RATIO:
            return "warn"
        if consecutive_repeats >= self.REPEAT_WARN_THRESHOLD:
            return "warn"
        return "ok"

    # =======================================================================
    # _execute_tool() — 工具执行适配层
    # =======================================================================
    async def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        if self._permission_engine:
            decision = self._permission_engine.check(name, args)
            if decision.action == "deny":
                return json.dumps({"status": "error", "error": f"权限拒绝: {decision.reason}"}, ensure_ascii=False)
            if decision.action == "prompt":
                if self._permission_callback:
                    approved = await self._permission_callback.on_prompt(name, args, decision.reason)
                    if not approved:
                        return json.dumps({"status": "error", "error": "用户拒绝执行"}, ensure_ascii=False)
                else:
                    return json.dumps({"status": "error", "error": f"需要确认但无回调: {decision.reason}"}, ensure_ascii=False)

        fn = self._registry.get_tool_fn(name)
        if fn is None:
            return json.dumps({"status": "error", "error": f"未知工具: {name}"}, ensure_ascii=False)
        try:
            return await fn(**args)
        except Exception as e:
            return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)

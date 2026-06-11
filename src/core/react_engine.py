from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import src.tools.registry as _default_registry
from src.utils.logger import logger


# ---------------------------------------------------------------------------
# 系统提示词
# ---------------------------------------------------------------------------
# 注入到每次 LLM 调用首条消息的 system prompt。
# 模型通过 function calling 机制自主决定调用哪个工具，不需要在 prompt 里描述工具列表。
SYSTEM_PROMPT = """你是一个代码开发助手。你的任务是理解用户需求，使用可用工具完成任务。

核心原则：
1. 先分析需求，制定计划（使用 todo_write 工具列出步骤），再逐步执行
2. 每次只调用一个工具，观察结果后再决定下一步
3. 遇到错误时分析原因，调整策略后重试
4. 保持代码简洁、可读、符合 Python 编码规范
5. 完成任务后直接回复最终结果，不要调用工具

可用工具通过 function calling 机制提供，请根据任务需要选择合适的工具。"""


class ReactEngine:
    """ReAct 循环引擎 — 对齐 Claude Code 设计。

    核心设计：
    - 使用 OpenAI 原生 function calling（非 JSON 解析），模型自主决定何时调用工具、何时停止
    - while True 无限循环，模型返回不带 tool_calls 的消息即自然终止
    - 双层安全网防止失控：token 用量上限 + 连续重复调用检测
    - 完整的 token 用量追踪（prompt / completion / cached）
    - TodoWrite 工具用于任务分解与进度跟踪
    """

    # -----------------------------------------------------------------------
    # 安全网常量
    # -----------------------------------------------------------------------
    # 默认最大 token 用量，达到后强制终止。128K 是 GPT-4o 上下文窗口的保守值。
    DEFAULT_MAX_TOKENS = 128_000
    # token 用量达到 80% 时注入提醒消息，提示模型尽快收尾。
    TOKEN_WARN_RATIO = 0.8
    # 同一工具 + 同一参数连续调用超过此次数则判定为死循环，强制终止。
    DEFAULT_MAX_CONSECUTIVE_REPEATS = 5
    # 连续重复达到 3 次时注入提醒消息。
    REPEAT_WARN_THRESHOLD = 3

    def __init__(
        self,
        llm_client: Any,
        tools_registry: Any = None,
        memory: Any = None,
        context: Any = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_consecutive_repeats: int = DEFAULT_MAX_CONSECUTIVE_REPEATS,
        permission_engine: Any = None,
        permission_callback: Any = None,
    ):
        self.llm_client = llm_client
        self._registry = tools_registry if tools_registry is not None else _default_registry
        self.memory = memory
        self.context = context
        self.max_tokens = max_tokens
        self.max_consecutive_repeats = max_consecutive_repeats
        self._permission_engine = permission_engine
        self._permission_callback = permission_callback

    # =======================================================================
    # run() — 异步执行入口，返回最终结果字典
    # =======================================================================
    async def run(self, task: str) -> dict[str, Any]:
        """执行 agent 循环，返回最终结果字典。

        返回值结构：
            success: bool          — 是否正常完成（安全网触发时为 False）
            answer: str            — 模型最终回复文本
            num_turns: int         — 总交互轮数
            total_tokens: int      — 总 token 用量
            prompt_tokens: int     — prompt token 用量
            completion_tokens: int — completion token 用量
            cached_tokens: int     — 缓存命中 token 数
            summary: str           — 仅在安全网触发时存在，描述终止原因
        """
        # ---- 初始化阶段 ----
        # 清空上一轮的记忆和上下文，确保每次 run 是独立执行
        if self.memory:
            self.memory.clear_memory()
        if self.context:
            self.context.add_context(f"用户任务: {task}")

        # 构建初始 messages 列表。
        # 采用累积式上下文管理：每轮 LLM 响应和工具结果都追加到 messages，
        # 模型能看到完整的执行历史，这是 Claude Code 的核心设计。
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        # 获取 OpenAI function calling 格式的工具定义列表
        tools = self._registry.get_openai_tools()

        # ---- 状态追踪变量 ----
        num_turns = 0                # 交互轮数计数器
        total_tokens = 0             # 累计 token 用量（用于安全网判断）
        total_prompt_tokens = 0      # 累计 prompt token
        total_completion_tokens = 0  # 累计 completion token
        total_cached_tokens = 0      # 累计缓存命中 token
        last_call: tuple[str, str] | None = None  # 上一轮的工具调用签名 (工具名, 参数JSON)
        consecutive_repeats = 0      # 连续重复调用计数

        # ===================================================================
        # 主循环 — 对齐 Claude Code 的 while(tool_use) 模式
        # ===================================================================
        # 循环终止条件只有两个：
        #   1. 模型返回不带 tool_calls 的消息 → 自然完成
        #   2. 安全网触发（token 超限 / 连续重复调用）→ 强制终止
        # 没有 max_iterations 硬上限，模型自主决定何时停止。
        while True:
            num_turns += 1

            # ---- 第 1 步：安全网检查 ----
            # 在每次 LLM 调用前检查，防止将已超限的上下文发送给 API。
            safety = self._check_safety(total_tokens, consecutive_repeats)
            if safety == "stop":
                logger.warning(f"安全网触发终止 | turns={num_turns} tokens={total_tokens}")
                return {
                    "success": False,
                    "answer": "",
                    "num_turns": num_turns,
                    "total_tokens": total_tokens,
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "cached_tokens": total_cached_tokens,
                    "summary": "安全网触发：任务终止",
                }
            elif safety == "warn":
                # 注入提醒消息，提示模型尽快收尾。
                # 消息以 user 角色注入，确保模型注意到。
                messages.append({"role": "user", "content": "⚠️ 系统提醒：请尽快总结当前进展并完成任务。"})

            # ---- 第 2 步：调用 LLM ----
            # 将完整 messages 历史 + 工具定义发送给模型。
            # 模型通过 function calling 机制决定：
            #   - 调用工具 → 返回 tool_calls
            #   - 任务完成 → 返回纯文本，无 tool_calls
            response = await self.llm_client.chat_async(
                messages=messages,
                temperature=0.3,
                tools=tools,
            )

            # ---- 第 3 步：累计 token 用量 ----
            # 从 API 响应的 usage 字段提取各项 token 统计。
            # prompt_tokens_details.cached_tokens 表示本次请求中被缓存命中的 token 数，
            # 可用于评估上下文复用效率。
            if hasattr(response, "usage") and response.usage:
                usage = response.usage
                total_tokens += usage.total_tokens or 0
                total_prompt_tokens += usage.prompt_tokens or 0
                total_completion_tokens += usage.completion_tokens or 0
                if usage.prompt_tokens_details and usage.prompt_tokens_details.cached_tokens:
                    total_cached_tokens += usage.prompt_tokens_details.cached_tokens

            # ---- 第 4 步：分支处理 ----
            if response.tool_calls:
                # ===========================================================
                # 分支 A：模型请求调用工具
                # ===========================================================

                # 4a. 将 assistant 消息（含 tool_calls）追加到 messages
                #     格式遵循 OpenAI function calling 协议：
                #     assistant 消息包含 content 和 tool_calls 数组
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
                tool_calls_msg = []
                for tc in response.tool_calls:
                    tool_calls_msg.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    })
                assistant_msg["tool_calls"] = tool_calls_msg
                messages.append(assistant_msg)

                # 4b. 逐个执行工具调用，将结果以 tool 角色追加到 messages
                for tc in response.tool_calls:
                    tool_name = tc.function.name
                    tool_args_str = tc.function.arguments

                    # ---- 连续重复调用检测 ----
                    # 比较当前调用签名与上一轮是否完全一致。
                    # 签名 = (工具名, 参数JSON字符串)，精确匹配。
                    # 连续相同 → consecutive_repeats 递增
                    # 不同 → 重置为 1
                    current_call = (tool_name, tool_args_str)
                    if current_call == last_call:
                        consecutive_repeats += 1
                    else:
                        consecutive_repeats = 1
                    last_call = current_call

                    # 解析工具参数 JSON
                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {}

                    # 执行工具
                    result = await self._execute_tool(tool_name, tool_args)

                    # 将工具执行结果以 tool 角色追加到 messages。
                    # tool_call_id 必须与 assistant 消息中的 id 对应，
                    # 这是 OpenAI function calling 协议的要求。
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

                    # 记录到外部 memory（供上层服务持久化）
                    if self.memory:
                        self.memory.add_observation({
                            "tool_name": tool_name,
                            "tool_args": tool_args,
                            "result": result,
                        })

                # 工具执行完毕，回到循环顶部，继续下一轮 LLM 调用。
                # 模型会看到工具结果，决定下一步操作。

            else:
                # ===========================================================
                # 分支 B：模型返回纯文本，无 tool_calls → 任务完成
                # ===========================================================
                # 这是唯一的正常退出路径。
                # 模型认为任务已完成，返回最终答案。
                logger.info(f"Agent 完成 | turns={num_turns} tokens={total_tokens}")
                return {
                    "success": True,
                    "answer": response.content or "",
                    "num_turns": num_turns,
                    "total_tokens": total_tokens,
                    "prompt_tokens": total_prompt_tokens,
                    "completion_tokens": total_completion_tokens,
                    "cached_tokens": total_cached_tokens,
                }

    # =======================================================================
    # iter_steps() — 异步流式生成器，供 WebSocket 实时推送
    # =======================================================================
    async def iter_steps(
        self,
        task: str,
        max_tokens: int | None = None,
        max_consecutive_repeats: int | None = None,
        start_iteration: int = 1,
        reset_state: bool = True,
        seed_observations: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """异步流式生成器，逐步 yield 执行步骤。

        与 run() 的核心逻辑完全一致，区别在于：
        - 每完成一个阶段（思考/行动/观察/答案）就 yield 一个事件
        - 调用方可以逐事件推送到 WebSocket，实现实时进度展示
        - 支持 resume 场景：通过 reset_state=False 和 seed_observations 恢复执行

        yield 的事件类型：
            thought:     模型返回的思考内容（含是否要调用工具）
            action:      模型决定调用的工具名和参数
            observation: 工具执行结果
            answer:      最终答案（正常完成或安全网触发）
        """
        # 允许调用方覆盖安全网参数
        token_limit = max_tokens if max_tokens is not None else self.max_tokens
        repeat_limit = max_consecutive_repeats if max_consecutive_repeats is not None else self.max_consecutive_repeats

        # 初始化：清空记忆和上下文（resume 场景可跳过）
        if reset_state:
            if self.memory:
                self.memory.clear_memory()
            if self.context:
                self.context.add_context(f"用户任务: {task}")

        # 构建初始 messages
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        tools = self._registry.get_openai_tools()

        # 状态追踪变量（与 run() 相同）
        num_turns = 0
        total_tokens = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_cached_tokens = 0
        last_call: tuple[str, str] | None = None
        consecutive_repeats = 0

        # 主循环 — 与 run() 逻辑完全一致，仅增加 yield 事件推送
        while True:
            num_turns += 1

            # 安全网检查
            safety = self._check_safety(total_tokens, consecutive_repeats, token_limit, repeat_limit)
            if safety == "stop":
                yield {
                    "type": "answer",
                    "iteration": num_turns,
                    "data": {"answer": "安全网触发：任务终止"},
                }
                return
            elif safety == "warn":
                messages.append({"role": "user", "content": "⚠️ 系统提醒：请尽快总结当前进展并完成任务。"})

            # 调用 LLM
            response = await self.llm_client.chat_async(
                messages=messages,
                temperature=0.3,
                tools=tools,
            )

            # 累计 token 用量
            if hasattr(response, "usage") and response.usage:
                usage = response.usage
                total_tokens += usage.total_tokens or 0
                total_prompt_tokens += usage.prompt_tokens or 0
                total_completion_tokens += usage.completion_tokens or 0
                if usage.prompt_tokens_details and usage.prompt_tokens_details.cached_tokens:
                    total_cached_tokens += usage.prompt_tokens_details.cached_tokens

            # yield 思考事件：模型本轮返回的内容 + 是否包含工具调用
            yield {
                "type": "thought",
                "iteration": num_turns,
                "data": {"content": response.content, "has_tool_calls": bool(response.tool_calls)},
            }

            if response.tool_calls:
                # 分支 A：工具调用 — 与 run() 相同的处理逻辑
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
                tool_calls_msg = []
                for tc in response.tool_calls:
                    tool_calls_msg.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    })
                assistant_msg["tool_calls"] = tool_calls_msg
                messages.append(assistant_msg)

                for tc in response.tool_calls:
                    tool_name = tc.function.name
                    tool_args_str = tc.function.arguments

                    # 连续重复调用检测
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

                    # yield 行动事件：告知调用方即将执行哪个工具
                    yield {
                        "type": "action",
                        "iteration": num_turns,
                        "data": {"tool": tool_name, "args": tool_args},
                    }

                    # 执行工具
                    result = await self._execute_tool(tool_name, tool_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })

                    # yield 观察事件：告知调用方工具执行结果
                    obs = {
                        "iteration": num_turns,
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "result": result,
                        "status": "success",
                        "error": None,
                        "execution_time": 0,
                    }
                    if self.memory:
                        self.memory.add_observation(obs)

                    yield {
                        "type": "observation",
                        "iteration": num_turns,
                        "data": obs,
                    }
            else:
                # 分支 B：任务完成
                yield {
                    "type": "answer",
                    "iteration": num_turns,
                    "data": {"answer": response.content or ""},
                }
                return

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
        """检查安全网状态，返回 "ok" / "warn" / "stop"。

        两层检测，按严重程度从高到低：

        第一层 — token 用量上限：
          - total_tokens >= max_tokens → "stop"  立即终止，防止超出上下文窗口
          - total_tokens >= 80% max_tokens → "warn"  提醒模型尽快收尾

        第二层 — 连续重复调用检测：
          - consecutive_repeats >= max_consecutive_repeats → "stop"  判定为死循环
          - consecutive_repeats >= REPEAT_WARN_THRESHOLD → "warn"  提醒模型换策略

        注意：stop 条件优先于 warn 条件，确保严重问题立即处理。
        """
        max_tok = token_limit if token_limit is not None else self.max_tokens
        max_rep = repeat_limit if repeat_limit is not None else self.max_consecutive_repeats

        # 第一层：token 用量 — 先检查 stop，再检查 warn
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
        """执行单个工具调用，返回 JSON 字符串结果。

        从工具注册表查找工具函数，执行并捕获异常。
        返回值统一为 JSON 字符串，包含 status 字段（"success" / "error"）。
        """
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

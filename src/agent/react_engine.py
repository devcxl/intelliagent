#!/usr/bin/env python3
"""
ReAct 循环引擎
实现 Reason → Act → Observe 循环，聚焦代码开发场景
"""
import asyncio
import inspect
import time
from functools import partial
from typing import AsyncGenerator, Awaitable, Callable, Dict, Any, List, Optional
from src.utils.logger import logger


class ReactEngine:
    """
    ReAct 循环引擎
    
    核心流程：
    1. Thought: LLM 思考下一步行动
    2. Action: 执行工具
    3. Observation: 观察结果并保存
    4. 重复直到任务完成或达到最大迭代次数
    """
    
    def __init__(
        self,
        llm_client,
        tools,
        memory,
        max_iterations: int = 10
    ):
        """
        初始化 ReAct 引擎
        
        Args:
            llm_client: LLM 客户端实例
            tools: 工具注册中心
            memory: 记忆管理器
            max_iterations: 最大迭代次数
        """
        self.llm_client = llm_client
        self.tools = tools
        self.memory = memory
        self.max_iterations = max_iterations
        
        logger.info("ReAct 引擎已初始化")

    def run(self, user_input: str, max_iterations: Optional[int] = None) -> Dict[str, Any]:
        """同步兼容入口。"""
        return asyncio.run(self.run_async(user_input, max_iterations=max_iterations))

    async def run_async(
        self,
        user_input: str,
        max_iterations: Optional[int] = None,
        *,
        start_iteration: int = 1,
        seed_observations: Optional[List[Dict[str, Any]]] = None,
        reset_state: bool = True,
        cancel_checker: Optional[Callable[[], bool | Awaitable[bool]]] = None,
    ) -> Dict[str, Any]:
        """
        执行异步 ReAct 循环。
        
        Args:
            user_input: 用户输入的任务描述
            max_iterations: 最大迭代次数（覆盖默认值）
        
        Returns:
            执行结果 {
                "success": bool,
                "summary": str,
                "iterations": int,
                "observations": List[Dict],
                "answer": str | None,
                "error": str | None
            }
        """
        effective_max_iterations = max_iterations or self.max_iterations
        self.max_iterations = effective_max_iterations

        start_time = time.time()
        all_observations = list(seed_observations or [])
        last_iteration = max(start_iteration - 1, 0)

        try:
            async for event in self.iter_steps(
                user_input,
                max_iterations=effective_max_iterations,
                start_iteration=start_iteration,
                seed_observations=seed_observations,
                reset_state=reset_state,
                cancel_checker=cancel_checker,
            ):
                last_iteration = event.get("iteration", last_iteration)

                if event["type"] == "observation":
                    all_observations.append(event["data"])
                    continue

                if event["type"] == "answer":
                    answer = event["data"].get("answer", "")
                    logger.info(f"✅ 任务完成 | 答案: {answer}")
                    return self._create_success_result(
                        iterations=last_iteration,
                        answer=answer,
                        observations=all_observations,
                        duration=time.time() - start_time,
                    )

                if event["type"] == "error":
                    return self._create_error_result(
                        iterations=max(last_iteration - 1, 0),
                        error=event.get("message", "无法生成 LLM 思考"),
                        observations=all_observations,
                    )

                if event["type"] == "cancelled":
                    return self._create_cancelled_result(
                        iterations=last_iteration,
                        observations=all_observations,
                        duration=time.time() - start_time,
                    )

                if event["type"] == "timeout":
                    return self._create_timeout_result(
                        iterations=effective_max_iterations,
                        observations=all_observations,
                        duration=time.time() - start_time,
                    )

            logger.warning(f"⚠️ 达到最大迭代次数 ({effective_max_iterations})")
            return self._create_timeout_result(
                iterations=effective_max_iterations,
                observations=all_observations,
                duration=time.time() - start_time,
            )

        except Exception as e:
            logger.error(f"❌ ReAct 循环异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return self._create_error_result(
                iterations=last_iteration,
                error=str(e),
                observations=all_observations,
            )

    async def iter_steps(
        self,
        user_input: str,
        max_iterations: Optional[int] = None,
        *,
        start_iteration: int = 1,
        seed_observations: Optional[List[Dict[str, Any]]] = None,
        reset_state: bool = True,
        cancel_checker: Optional[Callable[[], bool | Awaitable[bool]]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """按事件流异步执行 ReAct 循环。"""
        effective_max_iterations = max_iterations or self.max_iterations

        logger.info("=" * 60)
        logger.info(f"🚀 开始 ReAct 循环 | 任务: {user_input}")
        logger.info(f"最大迭代次数: {effective_max_iterations}")
        logger.info("=" * 60)

        self._prepare_run_state(
            user_input,
            seed_observations=seed_observations,
            reset_state=reset_state,
        )

        for iteration in range(start_iteration, effective_max_iterations + 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"📍 迭代 {iteration}/{effective_max_iterations}")
            logger.info(f"{'='*60}\n")

            if await self._should_cancel(cancel_checker):
                yield {
                    "type": "cancelled",
                    "iteration": max(iteration - 1, 0),
                    "message": "任务已取消",
                }
                return

            thought = await self._generate_thought_async(user_input, iteration)

            if not thought:
                logger.error("生成思考失败，终止循环")
                yield {
                    "type": "error",
                    "iteration": iteration,
                    "message": "无法生成 LLM 思考",
                }
                return

            logger.info(f"💭 Thought: {thought.get('reasoning', '无')}")
            yield {
                "type": "thought",
                "iteration": iteration,
                "data": {
                    "reasoning": thought.get("reasoning", ""),
                    "is_complete": thought.get("is_complete", False),
                },
            }

            if thought.get("is_complete"):
                yield {
                    "type": "answer",
                    "iteration": iteration,
                    "data": {"answer": thought.get("answer", "")},
                }
                return

            action = thought.get("action", {})
            tool_name = action.get("tool")
            tool_args = action.get("args", {})

            if not tool_name:
                logger.warning("⚠️ 未指定工具，跳过此次迭代")
                continue

            logger.info(f"🔧 Action: 调用工具 {tool_name}")
            logger.info(f"   参数: {tool_args}")
            yield {
                "type": "action",
                "iteration": iteration,
                "data": {"tool": tool_name, "args": tool_args},
            }

            if await self._should_cancel(cancel_checker):
                yield {
                    "type": "cancelled",
                    "iteration": max(iteration - 1, 0),
                    "message": "任务已取消",
                }
                return

            observation = await self._execute_and_observe_async(
                tool_name,
                tool_args,
                iteration,
            )
            yield {
                "type": "observation",
                "iteration": iteration,
                "data": observation,
            }

        yield {
            "type": "timeout",
            "iteration": effective_max_iterations,
            "message": "达到最大迭代次数",
        }

    def _prepare_run_state(
        self,
        user_input: str,
        *,
        seed_observations: Optional[List[Dict[str, Any]]] = None,
        reset_state: bool = True,
    ) -> None:
        if reset_state:
            self.memory.clear_memory()
            self.memory.add_context(f"用户任务: {user_input}")
            return

        for observation in seed_observations or []:
            self.memory.add_observation(observation)

        history = getattr(self.memory, "history", None)
        if not history:
            self.memory.add_context(f"用户任务: {user_input}")

    async def _should_cancel(
        self,
        cancel_checker: Optional[Callable[[], bool | Awaitable[bool]]],
    ) -> bool:
        if cancel_checker is None:
            return False

        result = cancel_checker()
        if inspect.isawaitable(result):
            return bool(await result)
        return bool(result)

    def _generate_thought(self, user_input: str, iteration: int) -> Optional[Dict[str, Any]]:
        """同步兼容入口。"""
        return asyncio.run(self._generate_thought_async(user_input, iteration))

    async def _generate_thought_async(self, user_input: str, iteration: int) -> Optional[Dict[str, Any]]:
        """
        生成 LLM 思考
        
        Args:
            user_input: 用户输入
            iteration: 当前迭代次数
        
        Returns:
            思考结果字典
        """
        try:
            available_tools = self.tools.list_tools()
            observations = self.memory.get_all_observations()

            generate_react_thought_async = getattr(
                self.llm_client,
                "generate_react_thought_async",
                None,
            )
            if inspect.iscoroutinefunction(generate_react_thought_async):
                thought = await self.llm_client.generate_react_thought_async(
                    user_input=user_input,
                    observations=observations,
                    available_tools=available_tools,
                )
            else:
                thought = await asyncio.to_thread(
                    self.llm_client.generate_react_thought,
                    user_input=user_input,
                    observations=observations,
                    available_tools=available_tools,
                )
            
            return thought
        
        except Exception as e:
            logger.error(f"生成思考失败 | error={e}")
            return None

    def _execute_and_observe(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        iteration: int
    ) -> Dict[str, Any]:
        """同步兼容入口。"""
        return asyncio.run(
            self._execute_and_observe_async(tool_name, tool_args, iteration)
        )

    async def _execute_and_observe_async(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        iteration: int,
    ) -> Dict[str, Any]:
        """
        执行工具并观察结果
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            iteration: 当前迭代次数
        
        Returns:
            观察结果字典
        """
        start_time = time.time()
        
        try:
            call_tool_async = getattr(self.tools, "call_tool_async", None)
            if inspect.iscoroutinefunction(call_tool_async):
                result = await self.tools.call_tool_async(tool_name, tool_args)
            else:
                if not hasattr(self.tools, '_initialized') or not self.tools._initialized:
                    await asyncio.to_thread(self.tools.initialize)

                tool_func = self.tools.get_tool(tool_name)
                result = await asyncio.to_thread(partial(tool_func, **tool_args))
            
            execution_time = time.time() - start_time
            
            # 构建观察结果
            observation = {
                "iteration": iteration,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": result,
                "status": "success",
                "error": None,
                "execution_time": execution_time
            }
            
            logger.info(f"✅ 工具执行成功 | 耗时: {execution_time:.2f}s")
            
            # 保存到记忆
            self.memory.add_observation(observation)
            
            return observation
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)
            
            # 构建失败观察结果
            observation = {
                "iteration": iteration,
                "tool_name": tool_name,
                "tool_args": tool_args,
                "result": None,
                "status": "failed",
                "error": error_msg,
                "execution_time": execution_time
            }
            
            logger.error(f"❌ 工具执行失败 | error={error_msg}")
            
            # 保存到记忆
            self.memory.add_observation(observation)
            
            return observation
    
    def _create_success_result(
        self,
        iterations: int,
        answer: str,
        observations: List[Dict],
        duration: float
    ) -> Dict[str, Any]:
        """创建成功结果"""
        return {
            "success": True,
            "summary": f"任务成功完成，经过 {iterations} 次迭代，耗时 {duration:.2f}s",
            "iterations": iterations,
            "answer": answer,
            "observations": observations,
            "error": None,
            "duration": duration
        }
    
    def _create_timeout_result(
        self,
        iterations: int,
        observations: List[Dict],
        duration: float
    ) -> Dict[str, Any]:
        """创建超时结果"""
        return {
            "success": False,
            "summary": f"达到最大迭代次数 ({iterations})，任务未完成，耗时 {duration:.2f}s",
            "iterations": iterations,
            "answer": None,
            "observations": observations,
            "error": "达到最大迭代次数",
            "duration": duration
        }

    def _create_cancelled_result(
        self,
        iterations: int,
        observations: List[Dict],
        duration: float,
    ) -> Dict[str, Any]:
        """创建取消结果。"""
        return {
            "success": False,
            "summary": f"任务已取消，执行到第 {iterations} 次迭代，耗时 {duration:.2f}s",
            "iterations": iterations,
            "answer": None,
            "observations": observations,
            "error": "任务已取消",
            "duration": duration,
        }
    
    def _create_error_result(
        self,
        iterations: int,
        error: str,
        observations: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            "success": False,
            "summary": f"任务执行出错: {error}",
            "iterations": iterations,
            "answer": None,
            "observations": observations or [],
            "error": error,
            "duration": 0
        }

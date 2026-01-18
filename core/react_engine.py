#!/usr/bin/env python3
"""
ReAct 循环引擎
实现 Reason → Act → Observe 循环，聚焦代码开发场景
"""
import time
from typing import Dict, Any, List, Optional
from utils.logger import logger


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
        context,
        max_iterations: int = 10
    ):
        """
        初始化 ReAct 引擎
        
        Args:
            llm_client: LLM 客户端实例
            tools: 工具注册中心
            memory: 记忆管理器
            context: 上下文管理器
            max_iterations: 最大迭代次数
        """
        self.llm_client = llm_client
        self.tools = tools
        self.memory = memory
        self.context = context
        self.max_iterations = max_iterations
        
        logger.info("ReAct 引擎已初始化")
    
    def run(self, user_input: str, max_iterations: Optional[int] = None) -> Dict[str, Any]:
        """
        执行 ReAct 循环
        
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
        if max_iterations:
            self.max_iterations = max_iterations
        
        logger.info("=" * 60)
        logger.info(f"🚀 开始 ReAct 循环 | 任务: {user_input}")
        logger.info(f"最大迭代次数: {self.max_iterations}")
        logger.info("=" * 60)
        
        # 清空之前的观察结果
        self.memory.clear_memory()
        
        # 添加任务到上下文
        self.context.add_context(f"用户任务: {user_input}")
        
        start_time = time.time()
        all_observations = []
        
        try:
            # ReAct 循环
            for iteration in range(1, self.max_iterations + 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"📍 迭代 {iteration}/{self.max_iterations}")
                logger.info(f"{'='*60}\n")
                
                # Step 1: Thought（LLM 思考）
                thought = self._generate_thought(user_input, iteration)
                
                if not thought:
                    logger.error("生成思考失败，终止循环")
                    return self._create_error_result(
                        iterations=iteration - 1,
                        error="无法生成 LLM 思考"
                    )
                
                # 记录思考
                logger.info(f"💭 Thought: {thought.get('reasoning', '无')}")
                
                # Step 2: 判断是否完成
                if thought.get("is_complete"):
                    answer = thought.get("answer", "")
                    logger.info(f"✅ 任务完成 | 答案: {answer}")
                    return self._create_success_result(
                        iterations=iteration,
                        answer=answer,
                        observations=all_observations,
                        duration=time.time() - start_time
                    )
                
                # Step 3: Action（执行工具）
                action = thought.get("action", {})
                tool_name = action.get("tool")
                tool_args = action.get("args", {})
                
                if not tool_name:
                    logger.warning("⚠️ 未指定工具，跳过此次迭代")
                    continue
                
                logger.info(f"🔧 Action: 调用工具 {tool_name}")
                logger.info(f"   参数: {tool_args}")
                
                # Step 4: 执行工具并观察结果
                observation = self._execute_and_observe(
                    tool_name,
                    tool_args,
                    iteration
                )
                # logger.info(f"工具调用结果：{observation}")
                
                all_observations.append(observation)
            
            # 达到最大迭代次数
            logger.warning(f"⚠️ 达到最大迭代次数 ({self.max_iterations})")
            return self._create_timeout_result(
                iterations=self.max_iterations,
                observations=all_observations,
                duration=time.time() - start_time
            )
        
        except Exception as e:
            logger.error(f"❌ ReAct 循环异常: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return self._create_error_result(
                iterations=iteration - 1,
                error=str(e),
                observations=all_observations
            )
    
    def _generate_thought(self, user_input: str, iteration: int) -> Optional[Dict[str, Any]]:
        """
        生成 LLM 思考
        
        Args:
            user_input: 用户输入
            iteration: 当前迭代次数
        
        Returns:
            思考结果字典
        """
        try:
            # 获取可用的工具列表
            available_tools = self.tools.list_tools()
            
            # 获取历史观察结果
            observations = self.memory.get_all_observations()
            
            # 调用 LLM 生成思考
            thought = self.llm_client.generate_react_thought(
                user_input=user_input,
                observations=observations,
                available_tools=available_tools
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
            # 初始化工具注册中心（如果需要）
            if not hasattr(self.tools, '_initialized') or not self.tools._initialized:
                self.tools.initialize()
            
            # 获取工具函数
            tool_func = self.tools.get_tool(tool_name)
            
            # 执行工具
            result = tool_func(**tool_args)
            
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

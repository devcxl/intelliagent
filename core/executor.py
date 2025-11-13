#!/usr/bin/env python3
"""
执行器模块 - PDCA 的 Do 阶段
负责执行计划中的各个步骤
"""
from typing import List, Dict, Any
from utils.logger import logger


class Executor:
    """任务执行器"""

    def __init__(self, tools, memory):
        """
        初始化执行器

        Args:
            tools: 工具注册中心
            memory: 记忆管理器
        """
        self.tools = tools
        self.memory = memory

    def execute_plan(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        执行计划中的所有步骤

        Args:
            plan: 执行计划列表

        Returns:
            执行结果列表，每个结果包含:
            - step_id: 步骤ID
            - status: 执行状态 ("success" | "failed" | "skipped")
            - result: 执行结果（如果成功）
            - error: 错误信息（如果失败）
        """
        logger.info("开始执行计划...")
        execution_results = []

        for step in plan:
            logger.info(f"➡️ 执行步骤 {step['id']}: {step['goal']}")
            
            # 执行单个步骤
            result = self._execute_step(step)
            execution_results.append(result)

        logger.info(f"计划执行完成 | 共执行 {len(execution_results)} 个步骤")
        return execution_results

    def _execute_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行单个步骤

        Args:
            step: 步骤信息 {"id", "goal", "tool", "args", "expected_outcome"}

        Returns:
            执行结果
        """
        tool_name = step.get("tool", "none")
        args = step.get("args", {})

        logger.info(f"🧩 调用工具: {tool_name} 参数: {args}")

        try:
            if tool_name == "none" or not tool_name:
                logger.warning("⚠️ 未指定工具，跳过执行")
                result = {
                    "step_id": step["id"],
                    "status": "skipped",
                    "reason": "未指定工具"
                }
                self.memory.add_observation(result)
                return result

            # 初始化工具注册中心（如果需要）
            if not hasattr(self.tools, '_initialized') or not self.tools._initialized:
                self.tools.initialize()

            # 获取工具
            tool_func = self.tools.get_tool(tool_name)

            # 执行工具
            tool_result = tool_func(**args)

            logger.info(f"✅ 工具执行成功")

            # 构建成功结果
            result = {
                "step_id": step["id"],
                "goal": step["goal"],
                "tool": tool_name,
                "args": args,
                "result": tool_result,
                "status": "success"
            }

            # 保存观察结果
            self.memory.add_observation(result)
            return result

        except Exception as e:
            logger.error(f"❌ 执行失败: {e}")
            
            # 构建失败结果
            result = {
                "step_id": step["id"],
                "goal": step["goal"],
                "tool": tool_name,
                "args": args,
                "error": str(e),
                "status": "failed"
            }

            # 保存观察结果
            self.memory.add_observation(result)
            return result

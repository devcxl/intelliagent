#!/usr/bin/env python3
"""
执行器模块 - PDCA 的 Act 阶段
负责根据检查结果决定重试、调整计划或记录经验
"""
from typing import Dict, Any, List, Optional
from utils.logger import logger


class Actor:
    """任务改进执行器"""

    def __init__(self, llm_client, memory, max_retry: int = 3):
        """
        初始化执行器

        Args:
            llm_client: LLM 客户端实例
            memory: 记忆管理器
            max_retry: 单个步骤最大重试次数
        """
        self.llm_client = llm_client
        self.memory = memory
        self.max_retry = max_retry
        self.retry_counts = {}  # 记录每个步骤的重试次数

    def decide_action(
        self,
        step: Dict[str, Any],
        execution_result: Dict[str, Any],
        check_result: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        根据检查结果决定下一步行动

        Args:
            step: 执行步骤
            execution_result: 执行结果
            check_result: 检查结果

        Returns:
            行动决策 {
                "action": "retry" | "skip" | "adjust_plan" | "continue",
                "reason": str
            }
        """
        step_id = step.get("id", 0)
        
        # 如果通过检查，继续下一步
        if check_result.get("passed", False):
            return {
                "action": "continue",
                "reason": "步骤执行成功"
            }

        # 获取当前重试次数
        current_retry = self.retry_counts.get(step_id, 0)

        # 如果还没超过最大重试次数且建议重试
        if current_retry < self.max_retry and check_result.get("needs_retry", False):
            self.retry_counts[step_id] = current_retry + 1
            logger.info(f"步骤 {step_id} 将重试 | 第 {current_retry + 1}/{self.max_retry} 次")
            return {
                "action": "retry",
                "reason": f"执行未通过，进行第 {current_retry + 1} 次重试"
            }

        # 超过重试次数或不建议重试，需要调整计划
        if current_retry >= self.max_retry:
            logger.warning(f"步骤 {step_id} 达到最大重试次数 | 需要调整计划")
            return {
                "action": "adjust_plan",
                "reason": f"已重试 {self.max_retry} 次仍未成功，需要调整计划"
            }

        # 其他情况，跳过该步骤
        return {
            "action": "skip",
            "reason": check_result.get("suggestion", "无法继续执行")
        }

    def adjust_plan(
        self,
        original_plan: List[Dict[str, Any]],
        failed_step: Dict[str, Any],
        error_info: str,
        available_tools: List[str]
    ) -> List[Dict[str, Any]]:
        """
        调整执行计划

        Args:
            original_plan: 原始计划
            failed_step: 失败的步骤
            error_info: 错误信息
            available_tools: 可用工具列表

        Returns:
            调整后的计划
        """
        logger.info(f"开始调整计划 | failed_step_id={failed_step.get('id')}")

        try:
            # 使用 LLM 生成新计划
            new_plan = self.llm_client.adjust_plan(
                original_plan=original_plan,
                failed_step=failed_step,
                error_info=error_info,
                available_tools=available_tools
            )

            # 重置重试计数
            self.retry_counts.clear()

            logger.info(f"计划调整完成 | new_steps={len(new_plan)}")
            return new_plan

        except Exception as e:
            logger.error(f"计划调整失败 | error={e}")
            # 返回原计划
            return original_plan

    def save_experience(
        self,
        task: str,
        plan: List[Dict[str, Any]],
        execution_results: List[Dict[str, Any]],
        check_results: List[Dict[str, Any]],
        final_status: str
    ):
        """
        保存任务执行经验

        Args:
            task: 原始任务描述
            plan: 执行计划
            execution_results: 执行结果列表
            check_results: 检查结果列表
            final_status: 最终状态 ("success" | "failed" | "partial")
        """
        try:
            experience = {
                "task": task,
                "plan": plan,
                "execution_results": execution_results,
                "check_results": check_results,
                "final_status": final_status,
                "total_steps": len(plan),
                "passed_steps": sum(1 for r in check_results if r.get("passed", False)),
                "average_score": sum(r.get("score", 0.0) for r in check_results) / len(check_results) if check_results else 0.0
            }

            # 保存到记忆模块
            self.memory.save_experience(experience)

            logger.info(
                f"经验已保存 | task={task[:50]}... "
                f"status={final_status} "
                f"score={experience['average_score']:.2f}"
            )

        except Exception as e:
            logger.error(f"保存经验失败 | error={e}")

    def get_similar_experiences(
        self,
        task: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        获取相似的历史经验

        Args:
            task: 当前任务描述
            top_k: 返回最相似的前k个经验

        Returns:
            相似经验列表
        """
        try:
            experiences = self.memory.get_similar_experiences(task, top_k)
            logger.info(f"找到 {len(experiences)} 个相似经验")
            return experiences

        except Exception as e:
            logger.error(f"获取相似经验失败 | error={e}")
            return []

    def reset_retry_counts(self):
        """重置所有步骤的重试计数"""
        self.retry_counts.clear()
        logger.debug("重试计数已重置")

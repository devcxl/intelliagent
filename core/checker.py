#!/usr/bin/env python3
"""
检查器模块 - PDCA 的 Check 阶段
负责验证任务执行结果的质量
"""
from typing import Dict, Any, Optional
from utils.logger import logger


class Checker:
    """任务结果检查器"""

    def __init__(self, llm_client):
        """
        初始化检查器

        Args:
            llm_client: LLM 客户端实例
        """
        self.llm_client = llm_client

    def check_step_result(
        self,
        step: Dict[str, Any],
        execution_result: Dict[str, Any],
        context: str = ""
    ) -> Dict[str, Any]:
        """
        检查单个步骤的执行结果

        Args:
            step: 执行步骤 {"id", "goal", "tool", "args", "expected_outcome"}
            execution_result: 执行结果 {"status", "result", "error"}
            context: 额外上下文信息

        Returns:
            检查结果 {
                "step_id": int,
                "passed": bool,
                "score": float,
                "feedback": str,
                "suggestion": str,
                "needs_retry": bool
            }
        """
        try:
            # 如果执行失败，直接标记为未通过
            if execution_result.get("status") == "failed":
                return {
                    "step_id": step["id"],
                    "passed": False,
                    "score": 0.0,
                    "feedback": f"执行失败: {execution_result.get('error', '未知错误')}",
                    "suggestion": "检查工具参数和执行环境",
                    "needs_retry": True
                }

            # 如果步骤被跳过
            if execution_result.get("status") == "skipped":
                return {
                    "step_id": step["id"],
                    "passed": False,
                    "score": 0.0,
                    "feedback": "步骤被跳过",
                    "suggestion": execution_result.get("reason", "未指定原因"),
                    "needs_retry": False
                }

            # 使用 LLM 进行质量检查
            goal = step.get("goal", "未指定目标")
            expected_outcome = step.get("expected_outcome", "未指定预期结果")
            actual_result = execution_result.get("result", {})

            llm_check = self.llm_client.check_result(
                goal=goal,
                expected_outcome=expected_outcome,
                actual_result=actual_result,
                context=context
            )

            # 构建检查结果
            check_result = {
                "step_id": step["id"],
                "passed": llm_check.get("passed", False),
                "score": llm_check.get("score", 0.0),
                "feedback": llm_check.get("feedback", "无反馈"),
                "suggestion": llm_check.get("suggestion", ""),
                "needs_retry": not llm_check.get("passed", False) and llm_check.get("score", 0.0) < 0.5
            }

            logger.info(
                f"步骤 {step['id']} 检查完成 | "
                f"passed={check_result['passed']} "
                f"score={check_result['score']:.2f}"
            )

            return check_result

        except Exception as e:
            logger.error(f"检查步骤 {step.get('id')} 失败 | error={e}")
            return {
                "step_id": step.get("id", 0),
                "passed": False,
                "score": 0.0,
                "feedback": f"检查过程出错: {str(e)}",
                "suggestion": "请检查检查器配置",
                "needs_retry": False
            }

    def check_plan_completion(
        self,
        plan: list,
        execution_results: list,
        check_results: list
    ) -> Dict[str, Any]:
        """
        检查整个计划的完成情况

        Args:
            plan: 执行计划
            execution_results: 所有步骤的执行结果
            check_results: 所有步骤的检查结果

        Returns:
            整体检查结果 {
                "overall_passed": bool,
                "total_steps": int,
                "passed_steps": int,
                "failed_steps": int,
                "average_score": float,
                "failed_step_ids": list,
                "summary": str
            }
        """
        try:
            total_steps = len(plan)
            passed_steps = sum(1 for r in check_results if r.get("passed", False))
            failed_steps = total_steps - passed_steps

            # 计算平均分数
            scores = [r.get("score", 0.0) for r in check_results]
            average_score = sum(scores) / len(scores) if scores else 0.0

            # 收集失败步骤ID
            failed_step_ids = [
                r.get("step_id") for r in check_results
                if not r.get("passed", False)
            ]

            # 判断整体是否通过（所有步骤都通过）
            overall_passed = failed_steps == 0

            summary = f"完成 {passed_steps}/{total_steps} 个步骤，平均得分 {average_score:.2f}"

            result = {
                "overall_passed": overall_passed,
                "total_steps": total_steps,
                "passed_steps": passed_steps,
                "failed_steps": failed_steps,
                "average_score": average_score,
                "failed_step_ids": failed_step_ids,
                "summary": summary
            }

            logger.info(f"计划检查完成 | {summary}")
            return result

        except Exception as e:
            logger.error(f"检查计划完成情况失败 | error={e}")
            return {
                "overall_passed": False,
                "total_steps": len(plan),
                "passed_steps": 0,
                "failed_steps": len(plan),
                "average_score": 0.0,
                "failed_step_ids": [],
                "summary": f"检查失败: {str(e)}"
            }

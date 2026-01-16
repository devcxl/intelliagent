#!/usr/bin/env python3
"""
PDCA 循环控制器
统一协调 Plan-Do-Check-Act 四个阶段
"""
from typing import Dict, Any, List, Optional
from utils.logger import logger


class PDCALoop:
    """PDCA 循环控制器"""

    def __init__(
        self,
        planner,
        executor,
        checker,
        actor,
        max_pdca_cycles: int = 3
    ):
        """
        初始化 PDCA 循环控制器

        Args:
            planner: 规划器 (Plan)
            executor: 执行器 (Do)
            checker: 检查器 (Check)
            actor: 改进器 (Act)
            max_pdca_cycles: 最大 PDCA 循环次数
        """
        self.planner = planner
        self.executor = executor
        self.checker = checker
        self.actor = actor
        self.max_pdca_cycles = max_pdca_cycles

    def run(self, user_input: str) -> Dict[str, Any]:
        """
        运行完整的 PDCA 循环

        Args:
            user_input: 用户输入的任务

        Returns:
            执行结果 {
                "success": bool,
                "cycles": int,
                "final_plan": list,
                "execution_results": list,
                "check_results": list,
                "summary": str,
                "execution_metrics": dict
            }
        """
        logger.info("=" * 60)
        logger.info(f"🚀 开始 PDCA 循环 | 任务: {user_input}")
        logger.info("=" * 60)

        cycle_count = 0
        current_plan = None
        all_execution_results = []
        all_check_results = []
        execution_metrics = {
            "total_steps": 0,
            "successful_steps": 0,
            "failed_steps": 0,
            "skipped_steps": 0,
            "total_retries": 0,
            "total_time": 0.0,
            "step_times": {}
        }

        while cycle_count < self.max_pdca_cycles:
            cycle_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"📍 PDCA 循环第 {cycle_count}/{self.max_pdca_cycles} 轮")
            logger.info(f"{'='*60}\n")

            # ============ PLAN 阶段 ============
            if current_plan is None:
                # 首次生成计划
                logger.info("📝 [PLAN] 生成执行计划...")
                try:
                    current_plan = self.planner.generate_plan(user_input)
                except Exception as e:
                    logger.error(f"LLM 调用失败 | error={e}")
                    logger.error("生成计划失败")
                    # 规划失败，继续重试（在下一轮）
                    current_plan = None
                    continue
                
                if not current_plan:
                    logger.error("计划生成失败")
                    return self._create_failure_result("计划生成失败", cycle_count)
                
                logger.info(f"✅ 计划生成完成 | 共 {len(current_plan)} 个步骤")
                for step in current_plan:
                    deps = step.get('dependencies', [])
                    dep_str = f" (依赖步骤: {deps})" if deps else ""
                    logger.info(f"   步骤 {step.get('id')}: {step.get('goal')}{dep_str}")

            # ============ DO 阶段 ============
            logger.info("⚙️  [DO] 执行计划（新的循环处理引擎）...")
            execution_results = self.executor.execute_plan(current_plan)
            all_execution_results.extend(execution_results)
            
            # 获取执行指标（来自新的 executor）
            execution_metrics = {
                "total_steps": self.executor.metrics.total_steps,
                "successful_steps": self.executor.metrics.successful_steps,
                "failed_steps": self.executor.metrics.failed_steps,
                "skipped_steps": self.executor.metrics.skipped_steps,
                "total_retries": self.executor.metrics.total_retries,
                "total_time": self.executor.metrics.total_time,
                "step_times": self.executor.metrics.step_times
            }
            
            logger.info(f"✅ 执行完成 | 成功: {execution_metrics['successful_steps']}, "
                       f"失败: {execution_metrics['failed_steps']}, "
                       f"跳过: {execution_metrics['skipped_steps']}")

            # ============ CHECK 阶段 ============
            logger.info("🔍 [CHECK] 检查执行结果...")
            check_results = []
            
            for step, exec_result in zip(current_plan, execution_results):
                check_result = self.checker.check_step_result(
                    step=step,
                    execution_result=exec_result,
                    context=self.executor.memory.get_recent_context()
                )
                check_results.append(check_result)
                
                status_emoji = "✅" if check_result["passed"] else "❌"
                logger.info(
                    f"   {status_emoji} 步骤 {step['id']}: "
                    f"{'通过' if check_result['passed'] else '未通过'} "
                    f"(得分: {check_result['score']:.2f})"
                )

            all_check_results.extend(check_results)

            # 检查整体完成情况
            completion_check = self.checker.check_plan_completion(
                plan=current_plan,
                execution_results=execution_results,
                check_results=check_results
            )

            logger.info(f"📊 整体检查: {completion_check['summary']}")

            # ============ ACT 阶段 ============
            logger.info("🎯 [ACT] 决策改进行动...")

            # 如果所有步骤都通过，任务完成
            if completion_check["overall_passed"]:
                logger.info("🎉 所有步骤执行成功！任务完成！")
                
                # 保存成功经验
                self.actor.save_experience(
                    task=user_input,
                    plan=current_plan,
                    execution_results=execution_results,
                    check_results=check_results,
                    final_status="success"
                )

                return {
                    "success": True,
                    "cycles": cycle_count,
                    "final_plan": current_plan,
                    "execution_results": all_execution_results,
                    "check_results": all_check_results,
                    "execution_metrics": execution_metrics,
                    "summary": f"任务成功完成，经过 {cycle_count} 轮 PDCA 循环"
                }

            # 处理失败的步骤
            has_adjusted = False
            for step, exec_result, check_result in zip(current_plan, execution_results, check_results):
                if not check_result["passed"]:
                    # 决定行动
                    action = self.actor.decide_action(step, exec_result, check_result)
                    
                    logger.info(
                        f"   步骤 {step['id']} 行动: {action['action']} - {action['reason']}"
                    )

                    # 如果需要调整计划
                    if action["action"] == "adjust_plan":
                        logger.info("🔄 调整执行计划...")
                        
                        error_info = exec_result.get("error", check_result.get("feedback", ""))
                        current_plan = self.actor.adjust_plan(
                            original_plan=current_plan,
                            failed_step=step,
                            error_info=error_info,
                            available_tools=self.planner.get_available_tools()
                        )
                        
                        logger.info(f"✅ 计划已调整 | 新计划 {len(current_plan)} 个步骤")
                        has_adjusted = True
                        break  # 跳出循环，开始新的 PDCA 轮次

            # 如果没有调整计划但还有失败步骤，继续下一轮（重试）
            if not has_adjusted and not completion_check["overall_passed"]:
                logger.info("⚠️  部分步骤未通过，将在下一轮重试")

        # 达到最大循环次数
        logger.warning(f"⚠️  达到最大 PDCA 循环次数 ({self.max_pdca_cycles})")
        
        # 保存部分成功的经验
        self.actor.save_experience(
            task=user_input,
            plan=current_plan,
            execution_results=all_execution_results,
            check_results=all_check_results,
            final_status="partial"
        )

        return {
            "success": False,
            "cycles": cycle_count,
            "final_plan": current_plan,
            "execution_results": all_execution_results,
            "check_results": all_check_results,
            "execution_metrics": execution_metrics,
            "summary": f"部分完成，经过 {cycle_count} 轮 PDCA 循环后仍有步骤未通过"
        }

    def _create_failure_result(self, reason: str, cycles: int) -> Dict[str, Any]:
        """创建失败结果"""
        return {
            "success": False,
            "cycles": cycles,
            "final_plan": [],
            "execution_results": [],
            "check_results": [],
            "execution_metrics": {
                "total_steps": 0,
                "successful_steps": 0,
                "failed_steps": 0,
                "skipped_steps": 0,
                "total_retries": 0,
                "total_time": 0.0,
                "step_times": {}
            },
            "summary": f"任务失败: {reason}"
        }

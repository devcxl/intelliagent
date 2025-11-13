#!/usr/bin/env python3
"""
规划器模块 - PDCA 的 Plan 阶段
使用 LLM 根据用户输入生成结构化执行计划
"""
from typing import List, Dict, Any
from utils.logger import logger


class Planner:
    """智能任务规划器"""

    def __init__(self, llm_client, tools, context):
        """
        初始化规划器

        Args:
            llm_client: LLM 客户端实例
            tools: 工具注册中心
            context: 上下文管理器
        """
        self.llm_client = llm_client
        self.tools = tools
        self.context = context

    def get_available_tools(self) -> List[str]:
        """
        获取可用工具列表

        Returns:
            工具名称列表
        """
        try:
            # 初始化工具注册中心（如果需要）
            if not hasattr(self.tools, '_initialized') or not self.tools._initialized:
                self.tools.initialize()

            # 获取所有可用工具
            available_tools = self.tools.list_tools()
            logger.debug(f"可用工具: {', '.join(available_tools)}")
            return available_tools

        except Exception as e:
            logger.error(f"获取工具列表失败 | error={e}")
            # 返回默认工具列表
            return ["run_shell", "read_file", "write_file", "run_tests", "git_status", "git_diff"]

    def generate_plan(self, user_input: str) -> List[Dict[str, Any]]:
        """
        使用 LLM 生成执行计划

        Args:
            user_input: 用户输入的任务描述

        Returns:
            执行计划列表，每个步骤包含:
            - id: 步骤编号
            - goal: 步骤目标
            - tool: 使用的工具
            - args: 工具参数
            - expected_outcome: 预期结果
        """
        try:
            txt = user_input.strip()
            if not txt:
                logger.warning("用户输入为空")
                return []

            # 获取可用工具
            available_tools = self.get_available_tools()

            # 获取上下文
            context = self.context.get_context()

            # 使用 LLM 生成计划
            logger.info("正在使用 LLM 生成执行计划...")
            plan = self.llm_client.generate_plan(
                user_input=txt,
                available_tools=available_tools,
                context=context
            )

            # 验证计划格式
            if not plan or not isinstance(plan, list):
                logger.error("LLM 返回的计划格式无效")
                return [{"id": 1, "goal": "计划生成失败", "tool": "none", "args": {}}]

            # 确保每个步骤都有必需的字段
            validated_plan = []
            for i, step in enumerate(plan, 1):
                if not isinstance(step, dict):
                    continue

                validated_step = {
                    "id": step.get("id", i),
                    "goal": step.get("goal", "未指定目标"),
                    "tool": step.get("tool", "none"),
                    "args": step.get("args", {}),
                    "expected_outcome": step.get("expected_outcome", "无具体预期")
                }
                validated_plan.append(validated_step)

            logger.info(f"计划生成成功 | 共 {len(validated_plan)} 个步骤")
            return validated_plan

        except Exception as e:
            logger.error(f"生成计划失败 | type={type(e).__name__} detail={e}")
            return [{"id": 1, "goal": "执行失败", "tool": "none", "args": {}, "expected_outcome": "无"}]

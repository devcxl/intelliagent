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
            return ["run_shell", "read_file", "write_file"]

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
            - dependencies: 依赖的步骤ID列表
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
                raise ValueError("LLM 返回的计划不是有效的列表格式")

            # 确保每个步骤都有必需的字段
            validated_plan = []
            for i, step in enumerate(plan, 1):
                if not isinstance(step, dict):
                    continue

                tool = step.get("tool")
                if not tool or tool == "none":
                    logger.warning(f"步骤 {i} 未指定有效工具，跳过此步骤")
                    continue

                validated_step = {
                    "id": step.get("id", i),
                    "goal": step.get("goal", "未指定目标"),
                    "tool": tool,
                    "args": step.get("args", {}),
                    "expected_outcome": step.get("expected_outcome", "无具体预期"),
                    "dependencies": step.get("dependencies", [])  # 支持依赖关系
                }
                validated_plan.append(validated_step)

            # 如果没有有效步骤，抛出异常
            if not validated_plan:
                raise ValueError("生成的计划中没有有效步骤（所有步骤都缺少工具）")

            logger.info(f"计划生成成功 | 共 {len(validated_plan)} 个步骤")
            return validated_plan

        except Exception as e:
            logger.error(f"生成计划失败 | type={type(e).__name__} detail={e}")
            # 抛出异常而不是返回无效步骤，让 PDCA 循环处理重试
            raise RuntimeError(f"规划失败: {e}")
    
    def analyze_dependencies(self, plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        分析执行计划中的依赖关系
        
        Args:
            plan: 执行计划列表
            
        Returns:
            带有自动分析依赖的计划
        """
        if not plan:
            return plan
            
        # 如果计划已经包含依赖信息，直接返回
        has_dependencies = any(step.get('dependencies') for step in plan)
        if has_dependencies:
            logger.info("计划已包含依赖信息，跳过自动分析")
            return plan
            
        # 分析隐式依赖（变量引用）
        import re
        analyzed_plan = []
        
        for step in plan:
            dependencies = []
            args_str = str(step.get('args', {}))
            
            # 查找 ${step_X.xxx} 的所有引用
            matches = re.findall(r'\$\{step_(\d+)\.', args_str)
            if matches:
                dependencies = list(set(int(m) for m in matches))
                dependencies.sort()
            
            step_copy = dict(step)
            step_copy['dependencies'] = dependencies
            analyzed_plan.append(step_copy)
            
            if dependencies:
                logger.info(f"步骤 {step.get('id')}: 自动检测依赖 {dependencies}")
        
        return analyzed_plan

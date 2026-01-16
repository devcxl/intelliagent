#!/usr/bin/env python3
"""
LLM 客户端模块
封装 OpenAI API 调用
"""
import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI
from utils.logger import logger


class LLMClient:
    """OpenAI LLM 客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o-mini"):
        """
        初始化 LLM 客户端

        Args:
            api_key: OpenAI API Key，如果为空则从环境变量读取
            model: 使用的模型名称
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_API_BASE")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY，请设置环境变量或传入参数")

        self.model = model
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        logger.info(f"LLM 客户端初始化完成 | model={self.model}")

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None
    ) -> str:
        """
        调用 OpenAI Chat API

        Args:
            messages: 消息列表 [{"role": "user/assistant/system", "content": "..."}]
            temperature: 温度参数 (0-2)
            max_tokens: 最大生成token数
            response_format: 响应格式，如 {"type": "json_object"}

        Returns:
            LLM 的回复内容
        """
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            if response_format:
                kwargs["response_format"] = response_format

            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            
            logger.debug(f"LLM 响应成功 | tokens={response.usage.total_tokens}")
            return content

        except Exception as e:
            logger.error(f"LLM 调用失败 | error={e}")
            raise

    def generate_plan(self, user_input: str, available_tools: List[str], context: str = "") -> List[Dict[str, Any]]:
        """
        生成执行计划

        Args:
            user_input: 用户输入
            available_tools: 可用工具列表
            context: 上下文信息

        Returns:
            执行计划列表
        """
        tool_descriptions = {
            "run_shell": "执行终端命令，参数 {\"cmd\": \"命令\"}",
            "read_file": "读取文件，参数 {\"path\": \"文件路径\"}",
            "write_file": "写入文件，参数 {\"path\": \"文件路径\", \"content\": \"内容\"}"
        }
        description_lines = []
        for tool in available_tools:
            if tool in tool_descriptions:
                description_lines.append(f"- {tool}: {tool_descriptions[tool]}")
            else:
                description_lines.append(f"- {tool}: 外部 MCP 工具（请参考对应服务定义）")
        tool_desc_text = "\n".join(description_lines) if description_lines else "- 无可用工具"

        system_prompt = f"""你是一个智能任务规划助手。根据用户输入，生成结构化的执行计划。

可用工具：
{', '.join(available_tools) if available_tools else '无'}

工具说明：
{tool_desc_text}

请将任务分解为多个步骤，每个步骤包含：
- id: 步骤编号（从1开始）
- goal: 步骤目标描述
- tool: 使用的工具名称
- args: 工具参数（JSON对象）
- expected_outcome: 预期结果描述

必须返回有效的 JSON 数组格式。"""

        user_prompt = f"""任务：{user_input}

{f"上下文：{context}" if context else ""}

请生成执行计划（JSON数组格式）："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.chat(
                messages=messages,
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            # 解析JSON响应
            result = json.loads(response)
            
            # 提取计划数组
            if "plan" in result:
                plan = result["plan"]
            elif "steps" in result:
                plan = result["steps"]
            elif isinstance(result, list):
                plan = result
            else:
                # 尝试找到第一个数组类型的值
                for value in result.values():
                    if isinstance(value, list):
                        plan = value
                        break
                else:
                    plan = []

            logger.info(f"生成计划成功 | steps={len(plan)}")
            return plan

        except json.JSONDecodeError as e:
            logger.error(f"解析计划JSON失败 | error={e}")
            return [{"id": 1, "goal": "解析失败", "tool": "none", "args": {}}]
        except Exception as e:
            logger.error(f"生成计划失败 | error={e}")
            return [{"id": 1, "goal": "生成失败", "tool": "none", "args": {}}]

    def check_result(
        self,
        goal: str,
        expected_outcome: str,
        actual_result: Any,
        context: str = ""
    ) -> Dict[str, Any]:
        """
        检查执行结果是否符合预期

        Args:
            goal: 任务目标
            expected_outcome: 预期结果
            actual_result: 实际执行结果
            context: 额外上下文

        Returns:
            检查结果 {"passed": bool, "score": float, "feedback": str, "suggestion": str}
        """
        system_prompt = """你是一个任务质量评估专家。评估任务执行结果是否符合预期。

请返回 JSON 格式的评估结果：
{
    "passed": true/false,  # 是否通过
    "score": 0.0-1.0,      # 质量评分
    "feedback": "评估反馈",
    "suggestion": "改进建议（如果未通过）"
}"""

        user_prompt = f"""任务目标：{goal}

预期结果：{expected_outcome}

实际结果：{json.dumps(actual_result, ensure_ascii=False, indent=2)}

{f"上下文：{context}" if context else ""}

请评估执行质量："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.chat(
                messages=messages,
                temperature=0.2,
                response_format={"type": "json_object"}
            )

            result = json.loads(response)
            logger.info(f"质量检查完成 | passed={result.get('passed')} score={result.get('score')}")
            return result

        except Exception as e:
            logger.error(f"质量检查失败 | error={e}")
            return {
                "passed": False,
                "score": 0.0,
                "feedback": f"检查失败: {str(e)}",
                "suggestion": "请检查任务执行过程"
            }

    def adjust_plan(
        self,
        original_plan: List[Dict[str, Any]],
        failed_step: Dict[str, Any],
        error_info: str,
        available_tools: List[str]
    ) -> List[Dict[str, Any]]:
        """
        根据失败信息调整执行计划

        Args:
            original_plan: 原始计划
            failed_step: 失败的步骤
            error_info: 错误信息
            available_tools: 可用工具列表

        Returns:
            调整后的执行计划
        """
        system_prompt = f"""你是一个智能计划调整助手。根据执行失败的信息，调整和优化执行计划。

可用工具：{', '.join(available_tools)}

请分析失败原因，重新生成优化后的执行计划（JSON数组格式）。"""

        user_prompt = f"""原始计划：
{json.dumps(original_plan, ensure_ascii=False, indent=2)}

失败步骤：
{json.dumps(failed_step, ensure_ascii=False, indent=2)}

错误信息：{error_info}

请生成调整后的计划："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = self.chat(
                messages=messages,
                temperature=0.4,
                response_format={"type": "json_object"}
            )

            result = json.loads(response)
            
            # 提取计划数组
            if "plan" in result:
                plan = result["plan"]
            elif "steps" in result:
                plan = result["steps"]
            elif isinstance(result, list):
                plan = result
            else:
                for value in result.values():
                    if isinstance(value, list):
                        plan = value
                        break
                else:
                    plan = original_plan

            logger.info(f"计划调整完成 | new_steps={len(plan)}")
            return plan

        except Exception as e:
            logger.error(f"计划调整失败 | error={e}")
            return original_plan

#!/usr/bin/env python3
"""
LLM 客户端模块
封装 OpenAI API 调用
"""
import asyncio
import os
import json
from typing import List, Dict, Any, Optional
from openai import OpenAI
from src.utils.logger import logger


class LLMClient:
    """OpenAI LLM 客户端"""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_API_BASE")
        if not self.api_key:
            raise ValueError("未找到 OPENAI_API_KEY，请设置环境变量或传入参数")

        self.model = model
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None
    ) -> str:
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

    async def chat_async(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> str:
        return await asyncio.to_thread(
            self.chat,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    def _format_observations(self, observations: List[Dict[str, Any]]) -> str:
        if not observations:
            return ""

        lines = []
        for obs in observations[-5:]:
            status = obs.get("status", "unknown")
            tool_name = obs.get("tool_name", "unknown")
            tool_args = obs.get("tool_args", {})
            result = obs.get("result")
            error = obs.get("error", "")

            if status == "success":
                lines.append(f"✓ 执行 {tool_name}，参数: {tool_args}")
                if result is not None:
                    lines.append(f"  结果: {result}")
            else:
                lines.append(f"✗ 执行 {tool_name} 失败: {error}")
                if tool_args:
                    lines.append(f"  参数: {tool_args}")

        return "\n".join(lines)

    def generate_react_thought(
        self,
        user_input: str,
        observations: List[Dict[str, Any]],
        available_tools: List[str],
        skills_context: str = "",
        full_skills_context: str = ""
    ) -> Dict[str, Any]:
        observations_text = self._format_observations(observations)

        tool_descriptions = {
            "run_shell": "执行终端命令，参数 {\"cmd\": \"命令字符串\"}",
            "read_file": "读取文件内容，参数 {\"path\": \"文件路径\"}",
            "write_file": "写入文件内容，参数 {\"path\": \"文件路径\", \"content\": \"内容\"}",
            "list_dir": "列出目录内容，参数 {\"path\": \"目录路径\"}",
            "delete_file": "删除文件，参数 {\"path\": \"文件路径\"}",
            "file_exists": "检查文件是否存在，参数 {\"path\": \"文件路径\"}",
        }
        description_lines = []
        for tool in available_tools:
            if tool in tool_descriptions:
                description_lines.append(f"- {tool}: {tool_descriptions[tool]}")
            else:
                description_lines.append(f"- {tool}: 外部 MCP 工具（请参考对应服务定义）")
        tool_desc_text = "\n".join(description_lines) if description_lines else "- 无可用工具"

        skills_section = ""
        if skills_context:
            skills_section = f"\n**可用的 Skill（摘要）：**\n\n{skills_context}\n"
        full_skills_section = ""
        if full_skills_context:
            full_skills_section = f"\n**Skill 详细定义（本轮已提供）：**\n\n{full_skills_context}\n"

        system_prompt = f"""你是一个代码开发助手，使用 ReAct（Reason + Act）循环解决任务。

**核心原则：**
1. 代码开发最佳实践：先分析需求、设计接口、编写测试、实现功能、运行 pytest、修复错误
2. 保持代码简洁、可读、符合 Python 编码规范
3. 每次行动只执行一个工具，观察结果后再决定下一步
4. 如遇到错误，分析原因并调整策略

**可用工具：**
{', '.join(available_tools) if available_tools else '无'}

**工具说明：**
{tool_desc_text}{skills_section}{full_skills_section}

**返回格式：**
必须返回 JSON 格式：

完成时：
{{
    "reasoning": "思考过程",
    "is_complete": true,
    "answer": "最终答案"
}}

继续执行时：
{{
    "reasoning": "思考过程",
    "is_complete": false,
    "action": {{
        "tool": "工具名称",
        "args": {{"参数名": "参数值"}}
    }}
}}"""

        user_prompt = f"""**任务：**
{user_input}

**历史观察：**
{observations_text if observations_text else "无"}

**请进行下一步思考：**"""

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

            result = json.loads(response)

            if "reasoning" not in result:
                result["reasoning"] = "无思考过程"
            if "is_complete" not in result:
                result["is_complete"] = False

            if result["is_complete"]:
                if "answer" not in result:
                    result["answer"] = ""
            else:
                if "action" not in result:
                    result["action"] = {"tool": "", "args": {}}

            logger.info(f"ReAct 思考生成 | is_complete={result['is_complete']}")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"解析 ReAct 思考 JSON 失败 | error={e}")
            return {
                "reasoning": "",
                "is_complete": False,
                "action": {"tool": "", "args": {}}
            }
        except Exception as e:
            logger.error(f"生成 ReAct 思考失败 | error={e}")
            return {
                "reasoning": f"错误: {str(e)}",
                "is_complete": False,
                "action": {"tool": "", "args": {}}
            }

    async def generate_react_thought_async(
        self,
        user_input: str,
        observations: List[Dict[str, Any]],
        available_tools: List[str],
        skills_context: str = "",
        full_skills_context: str = "",
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.generate_react_thought,
            user_input=user_input,
            observations=observations,
            available_tools=available_tools,
            skills_context=skills_context,
            full_skills_context=full_skills_context,
        )

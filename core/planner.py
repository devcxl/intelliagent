import re
from typing import List, Dict, Any
from utils.logger import logger

class Planner:
    def __init__(self, tools, context):
        self.tools = tools
        self.context = context

    def _help_alias(self, text: str) -> bool:
        return text.strip().lower() in {"help", "hel", "?"}

    def _parse_write(self, user_input: str) -> Dict[str, Any]:
        """支持格式: write <path> : <content>"""
        try:
            # 允许中文冒号
            parts = re.split(r"\s*:\s*|\s*：\s*", user_input, maxsplit=1)
            if len(parts) != 2:
                return {}
            left, content = parts
            left_parts = left.strip().split(maxsplit=1)
            if len(left_parts) != 2:
                return {}
            _, path = left_parts
            return {"path": path, "content": content}
        except Exception:
            return {}

    def generate_plan(self, user_input: str) -> List[Dict[str, Any]]:
        """
        规划器
        """
        try:
            txt = user_input.strip()
            
            return 

        except Exception as e:
            logger.error("生成计划失败 | type=%s detail=%r", type(e).__name__, e)
            return [{"id": 0, "goal": "执行失败", "tool": "none", "args": {}}]

#!/usr/bin/env python3
"""
记忆管理模块
管理任务执行的观察结果和历史经验
"""
import json
import os
from typing import List, Dict, Any
from src.utils.logger import logger


class Memory:
    """记忆管理器 - 支持观察结果、上下文历史和经验保存"""

    def __init__(self, experience_file: str = "experiences.json"):
        self.observations = []
        self.history = []
        self.experience_file = experience_file
        self.experiences = self._load_experiences()

    def add_observation(self, obs):
        self.observations.append(obs)
        logger.debug(f"添加观察结果 | total={len(self.observations)}")

    def add_context(self, msg):
        self.history.append(msg)

    def get_context(self) -> str:
        return "\n".join(self.history[-10:])

    def clear_context(self):
        self.history.clear()

    def clear_memory(self):
        self.observations.clear()
        self.history.clear()
        logger.debug("记忆已清空")

    def _load_experiences(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.experience_file):
            return []
        try:
            with open(self.experience_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载经验文件失败 | error={e}")
            return []

    def get_all_experiences(self) -> List[Dict[str, Any]]:
        return self.experiences

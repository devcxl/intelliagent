#!/usr/bin/env python3
"""
记忆管理模块
管理任务执行的观察结果和历史经验
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Any
from utils.logger import logger


class Memory:
    """增强型记忆管理器 - 支持观察结果和经验保存"""

    def __init__(self, experience_file: str = "experiences.json"):
        """
        初始化记忆管理器

        Args:
            experience_file: 经验保存文件路径
        """
        self.observations = []
        self.experience_file = experience_file
        self.experiences = self._load_experiences()

    def add_observation(self, obs):
        """
        添加观察结果

        Args:
            obs: 观察结果（字典或字符串）
        """
        self.observations.append(obs)
        logger.debug(f"添加观察结果 | total={len(self.observations)}")

    def get_recent_context(self, n: int = 5) -> str:
        """
        获取最近的观察结果

        Args:
            n: 返回最后n条记录

        Returns:
            格式化的上下文字符串
        """
        recent = self.observations[-n:] if len(self.observations) > n else self.observations
        return "\n".join(str(o) for o in recent)

    def get_all_observations(self) -> List[Any]:
        """
        获取所有观察结果

        Returns:
            观察结果列表
        """
        return self.observations

    def clear_memory(self):
        """清空观察结果（不清空经验库）"""
        self.observations.clear()
        logger.debug("观察结果已清空")

    # ============ 经验管理功能 ============

    def _load_experiences(self) -> List[Dict[str, Any]]:
        """
        从文件加载历史经验

        Returns:
            经验列表
        """
        if not os.path.exists(self.experience_file):
            logger.info(f"经验文件不存在，将创建新文件 | file={self.experience_file}")
            return []

        try:
            with open(self.experience_file, "r", encoding="utf-8") as f:
                experiences = json.load(f)
                logger.info(f"加载历史经验成功 | count={len(experiences)}")
                return experiences
        except Exception as e:
            logger.error(f"加载经验文件失败 | error={e}")
            return []

    def _save_experiences(self):
        """保存经验到文件"""
        try:
            with open(self.experience_file, "w", encoding="utf-8") as f:
                json.dump(self.experiences, f, ensure_ascii=False, indent=2)
            logger.debug(f"经验已保存 | count={len(self.experiences)}")
        except Exception as e:
            logger.error(f"保存经验文件失败 | error={e}")

    def save_experience(self, experience: Dict[str, Any]):
        """
        保存一次任务执行经验

        Args:
            experience: 经验数据，包含:
                - task: 任务描述
                - plan: 执行计划
                - execution_results: 执行结果
                - check_results: 检查结果
                - final_status: 最终状态
                - total_steps: 总步骤数
                - passed_steps: 通过步骤数
                - average_score: 平均分数
        """
        try:
            # 添加时间戳
            experience["timestamp"] = datetime.now().isoformat()
            
            # 添加到经验列表
            self.experiences.append(experience)
            
            # 保存到文件
            self._save_experiences()
            
            logger.info(
                f"经验已保存 | "
                f"task={experience.get('task', '')[:50]}... "
                f"status={experience.get('final_status')} "
                f"total_experiences={len(self.experiences)}"
            )

        except Exception as e:
            logger.error(f"保存经验失败 | error={e}")

    def get_similar_experiences(
        self,
        task: str,
        top_k: int = 3,
        min_score: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        获取与当前任务相似的历史经验

        Args:
            task: 当前任务描述
            top_k: 返回最相似的前k个经验
            min_score: 最低平均分数阈值（只返回成功的经验）

        Returns:
            相似经验列表
        """
        try:
            # 过滤出成功的经验
            successful_experiences = [
                exp for exp in self.experiences
                if exp.get("average_score", 0.0) >= min_score
            ]

            if not successful_experiences:
                logger.info("没有找到成功的历史经验")
                return []

            # 简单的相似度计算（基于关键词匹配）
            task_lower = task.lower()
            scored_experiences = []

            for exp in successful_experiences:
                exp_task = exp.get("task", "").lower()
                
                # 计算简单的文本相似度
                common_words = set(task_lower.split()) & set(exp_task.split())
                similarity = len(common_words) / max(len(task_lower.split()), 1)
                
                scored_experiences.append((similarity, exp))

            # 按相似度排序并返回前k个
            scored_experiences.sort(key=lambda x: x[0], reverse=True)
            similar = [exp for _, exp in scored_experiences[:top_k] if _ > 0]

            logger.info(f"找到 {len(similar)} 个相似经验")
            return similar

        except Exception as e:
            logger.error(f"获取相似经验失败 | error={e}")
            return []

    def get_all_experiences(self) -> List[Dict[str, Any]]:
        """
        获取所有历史经验

        Returns:
            所有经验列表
        """
        return self.experiences

    def clear_all_experiences(self):
        """清空所有经验（慎用）"""
        self.experiences.clear()
        self._save_experiences()
        logger.warning("所有历史经验已清空")


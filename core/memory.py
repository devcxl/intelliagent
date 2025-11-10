#!/usr/bin/env python3
"""
记忆管理模块
管理任务执行的观察结果和历史记录
"""


class Memory:
    """记忆管理器"""

    def __init__(self):
        """初始化记忆管理器"""
        self.observations = []

    def add_observation(self, obs):
        """添加观察结果"""
        self.observations.append(obs)

    def get_recent_context(self):
        """获取最近的观察结果（最后5条）"""
        return "\n".join(str(o) for o in self.observations[-5:])

    def get_all_observations(self):
        """获取所有观察结果"""
        return self.observations

    def clear_memory(self):
        """清空记忆"""
        self.observations.clear()


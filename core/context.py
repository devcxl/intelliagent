#!/usr/bin/env python3
"""
上下文管理模块
管理对话历史和环境信息
"""

class ContextManager:
    """上下文管理器"""

    def __init__(self):
        """初始化上下文管理器"""
        self.history = []

    def add_context(self, msg):
        """添加上下文消息"""
        self.history.append(msg)

    def get_context(self):
        """获取最近的上下文（最后10条）"""
        return "\n".join(self.history[-10:])

    def clear_context(self):
        """清空上下文"""
        self.history.clear()


#!/usr/bin/env python3
"""
上下文窗口策略模块 — 定义如何处理上下文窗口溢出。
"""

from __future__ import annotations

from typing import Any

from src.core.token_estimator import estimate_tokens
from src.utils.logger import logger


class WindowStrategy:
    """上下文窗口策略基类 — 定义如何处理上下文窗口溢出。

    子类需实现 apply 方法，在上下文超出 max_tokens 时执行具体的压缩策略。
    """

    def apply(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system_prompt: str,
    ) -> list[dict[str, Any]]:
        """当上下文超过 max_tokens 时，执行策略压缩上下文。

        Args:
            messages: 当前完整消息列表
            max_tokens: token 上限
            system_prompt: 系统提示词（应始终保留）

        Returns:
            压缩后的消息列表
        """
        raise NotImplementedError


class SlidingWindowStrategy(WindowStrategy):
    """滑动窗口策略 — 保留 system prompt + 最近的 N 条消息。

    当上下文超限时，丢弃最早的非 system/user 消息，
    保留最近的消息以维持对话连贯性。
    """

    def __init__(self, min_messages: int = 10, keep_first_n_user: int = 1):
        """
        Args:
            min_messages: 保留的最小消息数（system prompt 不计入）
            keep_first_n_user: 保留最早几条 user 消息（用于保留原始任务）
        """
        self.min_messages = min_messages
        self.keep_first_n_user = keep_first_n_user

    def apply(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        system_prompt: str,
    ) -> list[dict[str, Any]]:
        """滑动窗口截断：丢弃最早的历史消息，保留最近的上下文。

        保留 system prompt + 最早几条 user 消息 + 最近的 N 组消息。
        assistant 和对应的 tool 消息必须成组保留，避免孤立 tool 消息。

        Args:
            messages: 当前完整消息列表
            max_tokens: token 上限
            system_prompt: 系统提示词（应始终保留）

        Returns:
            截断后的消息列表
        """
        if not messages:
            return messages

        # 找到 system 消息的索引
        system_idx = -1
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                system_idx = i
                break

        # 分离 system prompt 和其余消息
        system_msg = messages[system_idx] if system_idx >= 0 else {"role": "system", "content": system_prompt}
        other_msgs = [m for i, m in enumerate(messages) if i != system_idx]

        # 估算当前 token 数
        current_estimate = self._estimate_tokens(messages)
        if current_estimate <= max_tokens:
            return messages  # 无需截断

        # 需要截断：保留最早几条 user 消息 + 最近的消息组。
        # assistant tool_calls 和对应 tool 消息必须成组保留，否则 OpenAI
        # function calling 协议会因为孤立 tool 消息而拒绝请求。
        early_user_msgs: list[dict[str, Any]] = []
        remaining: list[dict[str, Any]] = []
        for msg in other_msgs:
            if msg.get("role") == "user" and len(early_user_msgs) < self.keep_first_n_user:
                early_user_msgs.append(msg)
            else:
                remaining.append(msg)

        groups = self._group_messages(remaining)

        # 从最早的消息开始丢弃，直到 token 数满足要求
        # 但至少保留 min_messages 条（不含 system）
        while groups and len(early_user_msgs) + len(self._flatten(groups)) > self.min_messages:
            # 估算当前是否已满足
            test_msgs = [system_msg] + early_user_msgs + self._flatten(groups)
            if self._estimate_tokens(test_msgs) <= max_tokens:
                break
            # 丢弃最早的非早期消息
            groups.pop(0)

        truncated = [system_msg] + early_user_msgs + self._flatten(groups)
        logger.info(
            f"上下文窗口截断 | 原始 {len(messages)} 条 → {len(truncated)} 条"
            f" | 估算 tokens: {current_estimate} → {self._estimate_tokens(truncated)}"
        )
        return truncated

    @staticmethod
    def _group_messages(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        groups: list[list[dict[str, Any]]] = []
        i = 0
        while i < len(messages):
            msg = messages[i]
            if msg.get("role") == "tool":
                logger.warning(
                    "丢弃孤立 tool 消息 | tool_call_id=%s",
                    msg.get("tool_call_id"),
                )
                i += 1
                continue
            tool_calls = msg.get("tool_calls") if msg.get("role") == "assistant" else None
            if not tool_calls:
                groups.append([msg])
                i += 1
                continue

            expected_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}
            group = [msg]
            i += 1
            while i < len(messages) and messages[i].get("role") == "tool":
                if messages[i].get("tool_call_id") not in expected_ids:
                    break
                group.append(messages[i])
                i += 1
            groups.append(group)
        return groups

    @staticmethod
    def _flatten(groups: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        return [msg for group in groups for msg in group]

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        return estimate_tokens(messages)

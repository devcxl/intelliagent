#!/usr/bin/env python3
"""
上下文管理器 — 管理 ReAct 循环中的消息上下文。

核心职责：
1. 构建和维护 messages 列表（system + user + assistant + tool）
2. 支持消息追加、插入、替换、查询
3. 上下文窗口溢出处理（滑动窗口策略）
4. Token 用量追踪与安全网集成
5. 支持上下文快照持久化与恢复（用于 resume / rerun 场景）
6. 支持从数据库历史消息构建上下文（多轮对话延续）

设计原则：
- 单一职责：ContextManager 只管理"上下文"，不关心引擎的循环逻辑
- 无副作用：不直接操作数据库，只提供数据结构和策略
- 可插拔：可以通过策略模式替换溢出处理策略
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import logger

# ---------------------------------------------------------------------------
# 默认指令前缀
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = """你是一个代码开发助手。"""

DEFAULT_AGENT_PROMPT = """你的任务是理解用户需求，使用可用工具完成任务。

核心原则：
1. 先分析需求，制定计划（使用 todo_write 工具列出步骤），再逐步执行
2. 每次只调用一个工具，观察结果后再决定下一步
3. 遇到错误时分析原因，调整策略后重试
4. 保持代码简洁、可读、符合 Python 编码规范
5. 完成任务后直接回复最终结果，不要调用工具"""

DEFAULT_TOOLS_INSTRUCTION = """可用工具通过 function calling 机制提供，请根据任务需要选择合适的工具。"""

SUMMARY_PREFIX = "以下是已压缩的上下文摘要："

# ---------------------------------------------------------------------------
# Token 估算常量
# ---------------------------------------------------------------------------
# 粗略估算：中英文混编约 1 token ≈ 1.3 字符（中文约 1 token/字符，英文约 1 token/4字符）
TOKEN_PER_CHAR = 1.3
# 每条消息的开销（角色标记、格式等）
MESSAGE_OVERHEAD_TOKENS = 4
# 工具调用相关额外开销
TOOL_CALL_OVERHEAD_TOKENS = 10


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        total += MESSAGE_OVERHEAD_TOKENS
        content = msg.get("content", "")
        if content:
            total += int(len(str(content)) * TOKEN_PER_CHAR)
        if "tool_calls" in msg:
            total += TOOL_CALL_OVERHEAD_TOKENS * len(msg["tool_calls"])
    return total


# ===================================================================
# 上下文快照
# ===================================================================
@dataclass
class ContextSnapshot:
    """上下文快照 — 保存某一时刻的完整上下文状态，用于恢复和持久化。"""
    messages: list[dict[str, Any]] = field(default_factory=list)
    total_tokens_estimate: int = 0
    num_turns: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContextSummary:
    """压缩后的上下文摘要。"""
    content: str
    source_message_count: int
    compression_count: int


# ===================================================================
# 上下文窗口策略
# ===================================================================
class WindowStrategy:
    """上下文窗口策略基类 — 定义如何处理上下文窗口溢出。"""

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
        """滑动窗口截断：丢弃最早的历史消息，保留最近的上下文。"""
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


# ===================================================================
# ContextManager
# ===================================================================
class ContextManager:
    """上下文管理器 — 管理和维护 ReAct 循环的消息上下文。

    这是对 ReactEngine 中原生 messages 列表操作的抽象封装，
    提供更清晰、可扩展的上下文管理 API。

    使用方式：
        ctx = ContextManager(system_prompt=SYSTEM_PROMPT)
        ctx.initialize(task_text)
        ctx.add_assistant_message(content, tool_calls)
        ctx.add_tool_message(tool_call_id, content)
        ctx.add_user_message(content)

        for msg in ctx.get_messages():
            ...

        # 快照（用于持久化/恢复）
        snapshot = ctx.snapshot()
        ctx.restore(snapshot)

        # 上下文自动压缩
        ctx.compact_if_needed(max_tokens=128000)
    """

    def __init__(
        self,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        agent_prompt: str = DEFAULT_AGENT_PROMPT,
        tools_instruction: str = DEFAULT_TOOLS_INSTRUCTION,
        window_strategy: WindowStrategy | None = None,
        max_tokens: int = 128_000,
    ):
        """
        Args:
            system_prompt: 系统提示词
            agent_prompt: agent 行为指令
            tools_instruction: 工具使用指令
            window_strategy: 上下文窗口溢出处理策略（默认滑动窗口）
            max_tokens: 默认 token 上限
        """
        self._system_prompt = system_prompt
        self._agent_prompt = agent_prompt
        self._tools_instruction = tools_instruction
        self._window_strategy = window_strategy or SlidingWindowStrategy()
        self._max_tokens = max_tokens

        # 内部消息列表
        self._messages: list[dict[str, Any]] = []
        self._instruction_count = 0
        self._summary: ContextSummary | None = None
        # 元数据
        self._num_turns: int = 0
        self._metadata: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------
    @property
    def messages(self) -> list[dict[str, Any]]:
        """获取当前消息列表（只读视图）。"""
        return list(self._messages)

    @property
    def num_turns(self) -> int:
        """当前交互轮数。"""
        return self._num_turns

    @property
    def system_prompt(self) -> str:
        """系统提示词。"""
        return self._system_prompt

    @property
    def agent_prompt(self) -> str:
        """Agent 行为指令。"""
        return self._agent_prompt

    @property
    def tools_instruction(self) -> str:
        """工具使用指令。"""
        return self._tools_instruction

    @property
    def summary(self) -> ContextSummary | None:
        """当前上下文摘要。"""
        return self._summary

    @property
    def metadata(self) -> dict[str, Any]:
        """元数据字典。"""
        return self._metadata

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def initialize(
        self,
        task: str,
        history_context: str | None = None,
        seed_messages: list[dict[str, Any]] | None = None,
    ) -> None:
        """初始化上下文。

        构建 [system, user] 消息结构。如果提供了历史上下文，
        会将其拼接到 user 消息中。

        Args:
            task: 用户当前任务
            history_context: 历史消息摘要文本（来自数据库的历史对话）
            seed_messages: 种子消息列表（用于 resume 场景，直接恢复历史 messages）
        """
        self._messages = []
        self._num_turns = 0
        self._metadata = {}
        self._summary = None

        # 如果有种子消息，直接恢复（resume 场景）
        if seed_messages:
            self._messages = list(seed_messages)
            self._instruction_count = self._count_instruction_prefix(self._messages)
            return

        # 构建指令前缀
        instruction_messages = self._instruction_messages()
        self._messages.extend(instruction_messages)
        self._instruction_count = len(instruction_messages)

        # 构建 user 消息（含历史上下文）
        user_content = task
        if history_context:
            user_content = (
                f"{history_context}\n\n"
                f"现在的新任务是：{task}\n\n"
                "请结合上述对话历史，完成新任务。"
            )

        self._messages.append({"role": "user", "content": user_content})

    def clear(self) -> None:
        """清空上下文。"""
        self._messages = []
        self._instruction_count = 0
        self._summary = None
        self._num_turns = 0
        self._metadata = {}

    def compact_if_needed(
        self,
        max_tokens: int | None = None,
        ratio: float = 0.75,
        extra_tokens: int = 0,
    ) -> bool:
        """上下文达到阈值时自动压缩。"""
        limit = max_tokens if max_tokens is not None else self._max_tokens
        current_tokens = self.estimate_tokens()
        triggered = current_tokens + extra_tokens >= limit * ratio
        logger.debug(
            "ContextManager - 压缩检查 | current_tokens=%d limit=%d ratio=%.2f triggered=%s",
            current_tokens, limit, ratio, str(triggered).lower(),
        )
        if not triggered:
            return False
        self.compact_to_summary()
        return True

    def compact_to_summary(self) -> ContextSummary:
        """将非指令消息压缩为一条 summary message。"""
        instruction_messages = self._messages[:self._instruction_count] or self._instruction_messages()
        source_messages = [
            msg for msg in self._messages[len(instruction_messages):]
            if not self._is_summary_message(msg)
        ]
        old_summary = self._summary.content if self._summary else None
        summary_content = self._build_summary_content(source_messages, old_summary)
        compression_count = (self._summary.compression_count if self._summary else 0) + 1
        self._summary = ContextSummary(
            content=summary_content,
            source_message_count=len(source_messages),
            compression_count=compression_count,
        )
        self._messages = instruction_messages + [{"role": "user", "content": summary_content}]
        self._instruction_count = len(instruction_messages)
        logger.debug(
            "ContextManager - 压缩摘要 | source_msg_count=%d compression_count=%d",
            self._summary.source_message_count,
            self._summary.compression_count,
        )
        return self._summary

    def _instruction_messages(self) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": content}
            for content in (
                self._system_prompt,
                self._agent_prompt,
                self._tools_instruction,
            )
            if content
        ]

    @staticmethod
    def _count_instruction_prefix(messages: list[dict[str, Any]]) -> int:
        count = 0
        for msg in messages:
            if msg.get("role") != "system":
                break
            count += 1
        return count

    def _build_summary_content(
        self,
        messages: list[dict[str, Any]],
        old_summary: str | None = None,
    ) -> str:
        current_goal: list[str] = []
        constraints: list[str] = []
        completed: list[str] = []
        observations: list[str] = []

        if old_summary:
            observations.append(f"既有摘要：{old_summary}")

        for msg in messages:
            role = msg.get("role")
            raw_content = self._redact_secrets(str(msg.get("content") or ""))
            if self._is_summary_message(msg):
                continue
            elif role == "user":
                content = self._clip(raw_content, limit=2_000)
                target = current_goal if not current_goal else constraints
                target.append(content)
            elif role == "assistant":
                content = self._clip(raw_content, limit=500)
                if content:
                    completed.append(content)
                for tool_call in msg.get("tool_calls", []):
                    function = tool_call.get("function", {})
                    arguments = self._redact_secrets(str(function.get("arguments", "")))
                    observations.append(
                        f"工具调用 {function.get('name', '?')}({self._clip(arguments, limit=500)})"
                    )
            elif role == "tool":
                content = self._clip(raw_content, limit=500)
                observations.append(f"工具结果 {msg.get('tool_call_id', '?')}：{content}")

        return "\n".join([
            SUMMARY_PREFIX,
            "当前目标:",
            self._format_bullets(current_goal),
            "",
            "用户约束:",
            self._format_bullets(constraints),
            "",
            "已完成动作:",
            self._format_bullets(completed),
            "",
            "关键观察:",
            self._format_bullets(observations),
            "",
            "涉及文件:",
            "- 暂无明确文件",
            "",
            "待处理事项:",
            "- 继续完成当前目标",
            "",
            "下一步建议:",
            "- 根据本摘要继续执行下一步",
        ])

    @staticmethod
    def _format_bullets(items: list[str]) -> str:
        filtered = [item for item in items if item]
        if not filtered:
            return "- 无"
        return "\n".join(f"- {item}" for item in filtered)

    @staticmethod
    def _clip(value: str, limit: int = 240) -> str:
        return value if len(value) <= limit else value[:limit] + "..."

    @staticmethod
    def _redact_secrets(value: str) -> str:
        patterns = [
            r"sk-[A-Za-z0-9_-]+",
            r"Bearer\s+[A-Za-z0-9._~+/=-]+",
            r"(?i)(password\s*[=:]\s*)[^\s,;]+",
            r"(?i)(api_key\s*[=:]\s*)[^\s,;]+",
        ]
        redacted = value
        for pattern in patterns:
            redacted = re.sub(pattern, r"\1[REDACTED]" if "(" in pattern else "[REDACTED]", redacted)
        return redacted

    @staticmethod
    def _is_summary_message(msg: dict[str, Any]) -> bool:
        return msg.get("role") == "user" and str(msg.get("content", "")).startswith(SUMMARY_PREFIX)

    # ------------------------------------------------------------------
    # 消息追加
    # ------------------------------------------------------------------
    def add_assistant_message(
        self,
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> int:
        """追加一条 assistant 消息。

        Args:
            content: 消息文本内容
            tool_calls: 工具调用列表（OpenAI function calling 格式）

        Returns:
            消息在列表中的索引
        """
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self._messages.append(msg)
        logger.debug(
            "ContextManager - 添加消息 | role=assistant content_len=%d",
            len(content or ""),
        )
        return len(self._messages) - 1

    def add_tool_message(
        self,
        tool_call_id: str,
        content: str,
    ) -> int:
        """追加一条 tool 消息（工具执行结果）。

        Args:
            tool_call_id: 对应的工具调用 ID
            content: 工具执行结果

        Returns:
            消息在列表中的索引
        """
        msg: dict[str, Any] = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
        self._messages.append(msg)
        logger.debug(
            "ContextManager - 添加消息 | role=tool content_len=%d",
            len(content or ""),
        )
        return len(self._messages) - 1

    def add_user_message(self, content: str) -> int:
        """追加一条 user 消息。

        Args:
            content: 消息内容

        Returns:
            消息在列表中的索引
        """
        msg: dict[str, Any] = {"role": "user", "content": content}
        self._messages.append(msg)
        logger.debug(
            "ContextManager - 添加消息 | role=user content_len=%d",
            len(content or ""),
        )
        return len(self._messages) - 1

    def add_system_message(self, content: str) -> int:
        """追加一条 system 消息。

        Args:
            content: 消息内容

        Returns:
            消息在列表中的索引
        """
        msg: dict[str, Any] = {"role": "system", "content": content}
        self._messages.append(msg)
        return len(self._messages) - 1

    def increment_turns(self, n: int = 1) -> None:
        """递增轮数计数器。"""
        self._num_turns += n

    # ------------------------------------------------------------------
    # 消息查询
    # ------------------------------------------------------------------
    def get_messages(self) -> list[dict[str, Any]]:
        """获取完整消息列表（用于 LLM 调用）。"""
        return list(self._messages)

    def get_system_message(self) -> dict[str, Any] | None:
        """获取第一条 system 消息。"""
        for msg in self._messages:
            if msg.get("role") == "system":
                return msg
        return None

    def get_last_message(self) -> dict[str, Any] | None:
        """获取最后一条消息。"""
        return self._messages[-1] if self._messages else None

    def get_messages_by_role(self, role: str) -> list[dict[str, Any]]:
        """按角色获取消息。"""
        return [m for m in self._messages if m.get("role") == role]

    def count_messages(self) -> int:
        """消息总数。"""
        return len(self._messages)

    def count_tool_calls(self) -> int:
        """统计所有 assistant 消息中的工具调用总数。"""
        total = 0
        for msg in self._messages:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                total += len(msg["tool_calls"])
        return total

    # ------------------------------------------------------------------
    # Token 估算
    # ------------------------------------------------------------------
    def estimate_tokens(self) -> int:
        """估算当前消息列表的 token 总数。

        这是一个粗略估算，用于预判是否接近上下文窗口上限。
        实际 token 数以 API 返回的 usage 为准。
        """
        return self._estimate_tokens(self._messages)

    @staticmethod
    def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
        return estimate_tokens(messages)

    def should_truncate(
        self,
        max_tokens: int | None = None,
        ratio: float = 0.85,
    ) -> bool:
        """检查是否需要截断上下文。

        Args:
            max_tokens: token 上限（默认使用初始化时的值）
            ratio: 触发截断的阈值比例（默认 85%）

        Returns:
            是否需要截断
        """
        limit = max_tokens if max_tokens is not None else self._max_tokens
        estimate = self.estimate_tokens()
        return estimate >= limit * ratio

    def truncate(self, max_tokens: int | None = None) -> list[dict[str, Any]]:
        """执行上下文窗口溢出处理。

        Args:
            max_tokens: token 上限

        Returns:
            截断后的消息列表
        """
        limit = max_tokens if max_tokens is not None else self._max_tokens
        before_msgs = len(self._messages)
        tokens_before = self.estimate_tokens()
        self._messages = self._window_strategy.apply(
            self._messages, limit, self._system_prompt,
        )
        logger.debug(
            "ContextManager - 截断 | before_msgs=%d after_msgs=%d tokens_before=%d tokens_after=%d",
            before_msgs, len(self._messages), tokens_before, self.estimate_tokens(),
        )
        return self._messages

    # ------------------------------------------------------------------
    # 快照机制
    # ------------------------------------------------------------------
    def snapshot(self, metadata: dict[str, Any] | None = None) -> ContextSnapshot:
        """创建当前上下文的快照。

        Args:
            metadata: 附加元数据（如 conversation_id, run_id 等）

        Returns:
            上下文快照
        """
        snap_metadata = dict(self._metadata)
        if metadata:
            snap_metadata.update(metadata)

        return ContextSnapshot(
            messages=list(self._messages),
            total_tokens_estimate=self.estimate_tokens(),
            num_turns=self._num_turns,
            metadata=snap_metadata,
        )

    def restore(self, snapshot: ContextSnapshot) -> None:
        """从快照恢复上下文。

        Args:
            snapshot: 之前保存的上下文快照
        """
        self._messages = list(snapshot.messages)
        self._instruction_count = self._count_instruction_prefix(self._messages)
        self._summary = self._summary_from_messages(self._messages)
        self._num_turns = snapshot.num_turns
        self._metadata = dict(snapshot.metadata)
        logger.info(
            f"上下文从快照恢复 | messages={len(self._messages)} turns={self._num_turns}"
        )

    # ------------------------------------------------------------------
    # 序列化 / 反序列化
    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """将上下文序列化为字典（用于持久化存储）。"""
        return {
            "system_prompt": self._system_prompt,
            "agent_prompt": self._agent_prompt,
            "tools_instruction": self._tools_instruction,
            "messages": self._messages,
            "num_turns": self._num_turns,
            "metadata": self._metadata,
            "summary": self._summary.__dict__ if self._summary else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], **kwargs) -> "ContextManager":
        """从字典恢复 ContextManager 实例。

        Args:
            data: 包含上下文数据的字典
            **kwargs: 传递给构造函数的额外参数

        Returns:
            恢复的 ContextManager 实例
        """
        manager = cls(
            system_prompt=data.get("system_prompt", DEFAULT_SYSTEM_PROMPT),
            agent_prompt=data.get("agent_prompt", DEFAULT_AGENT_PROMPT),
            tools_instruction=data.get("tools_instruction", DEFAULT_TOOLS_INSTRUCTION),
            **kwargs,
        )
        manager._messages = list(data.get("messages", []))
        manager._instruction_count = manager._count_instruction_prefix(manager._messages)
        manager._num_turns = data.get("num_turns", 0)
        manager._metadata = dict(data.get("metadata", {}))
        summary_data = data.get("summary")
        if summary_data:
            manager._summary = ContextSummary(**summary_data)
        else:
            manager._summary = manager._summary_from_messages(manager._messages)
        return manager

    @classmethod
    def _summary_from_messages(cls, messages: list[dict[str, Any]]) -> ContextSummary | None:
        for msg in messages:
            if cls._is_summary_message(msg):
                return ContextSummary(
                    content=str(msg.get("content", "")),
                    source_message_count=0,
                    compression_count=1,
                )
        return None

    # ------------------------------------------------------------------
    # 构建历史上下文字符串（用于 main.py 的多轮对话延续）
    # ------------------------------------------------------------------
    @staticmethod
    def build_history_context(
        history_messages: list[dict[str, Any]],
        max_messages: int = 20,
        max_content_length: int = 500,
    ) -> str | None:
        """将数据库中的历史消息构建为上下文字符串。

        这个函数用于多轮对话场景：从数据库加载历史消息后，
        将其格式化为一段文本，拼接到新的 user 消息前面。

        Args:
            history_messages: 历史消息列表（来自数据库）
            max_messages: 最多保留多少条最近消息
            max_content_length: 单条消息最大截断长度

        Returns:
            格式化后的历史上下文字符串，若历史为空则返回 None
        """
        if not history_messages:
            return None

        recent = history_messages[-max_messages:]

        lines = ["以下是之前的对话历史（供参考上下文）：", "---"]
        for msg in recent:
            role = msg.get("role", "?").upper()
            content = msg.get("content", "")
            if len(content) > max_content_length:
                content = content[:max_content_length] + "..."
            lines.append(f"[{role}] {content}")
        lines.append("---")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"ContextManager(messages={len(self._messages)}, "
            f"turns={self._num_turns}, "
            f"tokens_est={self.estimate_tokens()})"
        )


__all__ = [
    "ContextManager",
    "ContextSnapshot",
    "ContextSummary",
    "WindowStrategy",
    "SlidingWindowStrategy",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_AGENT_PROMPT",
    "DEFAULT_TOOLS_INSTRUCTION",
]

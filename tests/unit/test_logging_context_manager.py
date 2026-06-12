#!/usr/bin/env python3
"""
ContextManager DEBUG 日志测试

使用 caplog fixture 验证 DEBUG 级别日志输出。
"""

import logging

import pytest

from src.core.context_manager import ContextManager, SlidingWindowStrategy


@pytest.fixture(autouse=True)
def _enable_debug_logging():
    """确保 intelliagent logger 能输出 DEBUG 级别日志。"""
    logging.getLogger("intelliagent").setLevel(logging.DEBUG)


class TestAddMessageDebugLogs:
    """add_*_message() 方法的 DEBUG 日志"""

    def test_add_assistant_message_logs_role_and_content_len(self, caplog):
        ctx = ContextManager()
        ctx.initialize("测试任务")

        with caplog.at_level(logging.DEBUG):
            ctx.add_assistant_message("这是一条助手回复")

        assert "ContextManager - 添加消息" in caplog.text
        assert "role=assistant" in caplog.text
        assert "content_len=" in caplog.text

    def test_add_tool_message_logs_role_and_content_len(self, caplog):
        ctx = ContextManager()
        ctx.initialize("测试任务")

        with caplog.at_level(logging.DEBUG):
            ctx.add_tool_message("call-1", "工具执行结果")

        assert "ContextManager - 添加消息" in caplog.text
        assert "role=tool" in caplog.text
        assert "content_len=" in caplog.text

    def test_add_user_message_logs_role_and_content_len(self, caplog):
        ctx = ContextManager()
        ctx.initialize("测试任务")

        with caplog.at_level(logging.DEBUG):
            ctx.add_user_message("用户的新消息")

        assert "ContextManager - 添加消息" in caplog.text
        assert "role=user" in caplog.text
        assert "content_len=" in caplog.text


class TestCompactIfNeededDebugLogs:
    """compact_if_needed() 的 DEBUG 日志"""

    def test_compact_if_needed_logs_check_info_when_not_triggered(self, caplog):
        ctx = ContextManager(max_tokens=10000)
        ctx.initialize("测试任务")

        with caplog.at_level(logging.DEBUG):
            ctx.compact_if_needed()

        assert "ContextManager - 压缩检查" in caplog.text
        assert "current_tokens=" in caplog.text
        assert "limit=" in caplog.text
        assert "ratio=" in caplog.text
        assert "triggered=false" in caplog.text

    def test_compact_if_needed_logs_check_info_when_triggered(self, caplog):
        ctx = ContextManager(max_tokens=100)
        ctx.initialize("测试任务")
        ctx.add_assistant_message("x" * 200)

        with caplog.at_level(logging.DEBUG):
            ctx.compact_if_needed()

        assert "ContextManager - 压缩检查" in caplog.text
        assert "triggered=true" in caplog.text


class TestCompactToSummaryDebugLogs:
    """compact_to_summary() 的 DEBUG 日志"""

    def test_compact_to_summary_logs_source_msg_count_and_compression_count(self, caplog):
        ctx = ContextManager(
            system_prompt="system",
            agent_prompt="agent",
            tools_instruction="tools",
            max_tokens=80,
        )
        ctx.initialize("测试任务")
        ctx.add_assistant_message("完成动作")

        with caplog.at_level(logging.DEBUG):
            ctx.compact_to_summary()

        assert "ContextManager - 压缩摘要" in caplog.text
        assert "source_msg_count=" in caplog.text
        assert "compression_count=" in caplog.text


class TestTruncateDebugLogs:
    """truncate() 的 DEBUG 日志"""

    def test_truncate_logs_before_and_after_stats(self, caplog):
        ctx = ContextManager(
            system_prompt="system",
            window_strategy=SlidingWindowStrategy(min_messages=1),
            max_tokens=80,
        )
        ctx.initialize("原始任务")
        ctx.add_user_message("x" * 200)

        with caplog.at_level(logging.DEBUG):
            ctx.truncate(max_tokens=80)

        assert "ContextManager - 截断" in caplog.text
        assert "before_msgs=" in caplog.text
        assert "after_msgs=" in caplog.text
        assert "tokens_before=" in caplog.text
        assert "tokens_after=" in caplog.text

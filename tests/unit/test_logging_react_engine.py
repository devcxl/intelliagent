#!/usr/bin/env python3
"""
ReactEngine._loop() DEBUG 日志测试

使用 caplog fixture 验证 DEBUG 级别日志输出。
"""
import logging
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.react_engine import ReactEngine


@pytest.fixture(autouse=True)
def _enable_debug_logging():
    """确保 intelliagent logger 在测试期间输出 DEBUG 级别日志。"""
    import src.utils.logger as logger_mod
    logger_mod.logger.setLevel(logging.DEBUG)
    logging.getLogger("intelliagent").setLevel(logging.DEBUG)


def _make_tool_call(id: str, name: str, arguments: str):
    tc = Mock()
    tc.id = id
    tc.function = Mock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _make_response(content: str | None = None, tool_calls: list | None = None,
                   total_tokens: int = 100, prompt_tokens: int = 80,
                   completion_tokens: int = 20):
    resp = Mock()
    resp.content = content
    resp.tool_calls = tool_calls or []
    resp.usage = Mock()
    resp.usage.total_tokens = total_tokens
    resp.usage.prompt_tokens = prompt_tokens
    resp.usage.completion_tokens = completion_tokens
    resp.usage.prompt_tokens_details = Mock()
    resp.usage.prompt_tokens_details.cached_tokens = 0
    return resp


@pytest.fixture
def mock_engine():
    llm = AsyncMock()
    memory = Mock()
    context = Mock()
    engine = ReactEngine(
        llm_client=llm,
        memory=memory,
        context=context,
        max_tokens=10000,
        max_consecutive_repeats=5,
    )
    return engine


class TestReactEngineLoopDebugLogs:

    @pytest.mark.asyncio
    async def test_loop_start_logs_task_and_limits(self, mock_engine, caplog):
        """循环开始时输出 task/token_limit/repeat_limit/iteration_limit"""
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("修复 bug")

        assert "ReactEngine - 循环开始" in caplog.text
        assert "task=修复 bug" in caplog.text
        assert "token_limit=10000" in caplog.text
        assert "repeat_limit=5" in caplog.text

    @pytest.mark.asyncio
    async def test_turn_start_logs_turn_number_and_tokens(self, mock_engine, caplog):
        """每轮迭代开始时输出轮次和累计 token"""
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(
                tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "a.txt"}')],
                total_tokens=100,
            ),
            _make_response(content="完成", total_tokens=50),
        ]

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 第 1 轮开始" in caplog.text
        assert "ReactEngine - 第 2 轮开始" in caplog.text

    @pytest.mark.asyncio
    async def test_llm_call_before_logs_msg_count_and_estimate(self, mock_engine, caplog):
        """LLM 调用前输出 msg_count 和 token_estimate"""
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - LLM 调用前" in caplog.text
        assert "msg_count=" in caplog.text

    @pytest.mark.asyncio
    async def test_llm_call_after_logs_token_details(self, mock_engine, caplog):
        """LLM 调用后输出 token 详情"""
        mock_engine.llm_client.chat_async.return_value = _make_response(
            content="完成", total_tokens=150, prompt_tokens=100, completion_tokens=50,
        )

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - LLM 调用后" in caplog.text
        assert "total_tokens=150" in caplog.text
        assert "prompt_tokens=100" in caplog.text
        assert "completion_tokens=50" in caplog.text

    @pytest.mark.asyncio
    async def test_safety_check_logs_result(self, mock_engine, caplog):
        """安全网检查输出 result/tokens/repeats"""
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 安全网检查" in caplog.text
        assert "result=ok" in caplog.text

    @pytest.mark.asyncio
    async def test_tool_execution_logs_tool_name_and_args_len(self, mock_engine, caplog):
        """工具执行输出 tool 名称和参数长度"""
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(
                tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "/tmp/test.txt"}')],
            ),
            _make_response(content="完成"),
        ]

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 执行工具" in caplog.text
        assert "tool=read_file" in caplog.text
        assert "args_len=" in caplog.text

    @pytest.mark.asyncio
    async def test_tool_result_logs_result_len(self, mock_engine, caplog):
        """工具结果输出 result_len"""
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(
                tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "/tmp/test.txt"}')],
            ),
            _make_response(content="完成"),
        ]

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 工具结果" in caplog.text
        assert "tool=read_file" in caplog.text
        assert "result_len=" in caplog.text

    @pytest.mark.asyncio
    async def test_loop_exit_logs_reason_when_agent_finished(self, mock_engine, caplog):
        """Agent 正常完成时输出退出原因"""
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 循环退出" in caplog.text
        assert "reason=agent_finished" in caplog.text

    @pytest.mark.asyncio
    async def test_loop_exit_logs_reason_when_token_limit(self, mock_engine, caplog):
        """Token 超限时输出退出原因"""
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')],
            total_tokens=10000,
        )

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 循环退出" in caplog.text
        assert "reason=safety_stop" in caplog.text

    @pytest.mark.asyncio
    async def test_loop_exit_logs_reason_when_max_iterations(self, mock_engine, caplog):
        """达到最大轮数时输出退出原因"""
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')],
            total_tokens=10,
        )

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务", max_iterations=2)

        assert "ReactEngine - 循环退出" in caplog.text
        assert "reason=max_iterations" in caplog.text

    @pytest.mark.asyncio
    async def test_compact_before_logs_trigger(self, mock_engine, caplog):
        """compact_if_needed 触发时输出日志"""
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 压缩上下文前" in caplog.text

    @pytest.mark.asyncio
    async def test_compact_after_logs_result(self, mock_engine, caplog):
        """compact_if_needed 执行后输出结果"""
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        with caplog.at_level(logging.DEBUG):
            await mock_engine.run("测试任务")

        assert "ReactEngine - 压缩上下文后" in caplog.text

#!/usr/bin/env python3
"""ReactEngine DEBUG 日志测试 — 验证关键步骤输出日志。"""

import logging
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.react_engine import ReactEngine


@pytest.fixture(autouse=True)
def _enable_debug_logging():
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


def _make_response(
    content: str | None = None,
    tool_calls: list | None = None,
    total_tokens: int = 100,
    prompt_tokens: int = 80,
    completion_tokens: int = 20,
):
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
    engine = ReactEngine(
        llm_client=llm,
        memory=memory,
        context_limit=10000,
    )
    return engine


class TestReactEngineDebugLogs:
    @pytest.mark.asyncio
    async def test_logs_step_info(self, mock_engine, caplog):
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        await mock_engine.run("测试任务")

        assert "第 1 轮" in caplog.text
        assert "Agent 完成" in caplog.text

    @pytest.mark.asyncio
    async def test_logs_tool_call_info(self, mock_engine, caplog):
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(tool_calls=[_make_tool_call("c1", "read_file", '{"path": "test.txt"}')]),
            _make_response(content="完成"),
        ]

        await mock_engine.run("读取文件")

        assert "第 2 轮" in caplog.text
        assert "Agent 完成" in caplog.text

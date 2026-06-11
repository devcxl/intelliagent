#!/usr/bin/env python3
"""
ReAct 循环引擎单元测试 — function calling 模式 + 双层安全网
"""
import pytest
from unittest.mock import AsyncMock, Mock

from src.core.react_engine import ReactEngine


def _make_tool_call(id: str, name: str, arguments: str):
    tc = Mock()
    tc.id = id
    tc.function = Mock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _make_response(content: str | None = None, tool_calls: list | None = None, total_tokens: int = 100):
    resp = Mock()
    resp.content = content
    resp.tool_calls = tool_calls or []
    resp.usage = Mock()
    resp.usage.total_tokens = total_tokens
    resp.usage.prompt_tokens = 80
    resp.usage.completion_tokens = 20
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


class TestReactEngineBasicRun:

    @pytest.mark.asyncio
    async def test_immediate_completion(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            content="任务已完成，答案是 42"
        )

        result = await mock_engine.run("测试任务")

        assert result["success"] is True
        assert result["answer"] == "任务已完成，答案是 42"
        assert result["num_turns"] == 1
        assert "total_tokens" in result
        assert "prompt_tokens" in result
        assert "completion_tokens" in result
        assert "cached_tokens" in result

    @pytest.mark.asyncio
    async def test_token_limit_stops(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')],
            total_tokens=10000,
        )

        result = await mock_engine.run("测试任务")

        assert result["success"] is False
        assert "安全网触发" in result["summary"]

    @pytest.mark.asyncio
    async def test_consecutive_repeats_stops(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "same.txt"}')],
            total_tokens=10,
        )

        result = await mock_engine.run("测试任务")

        assert result["success"] is False
        assert "安全网触发" in result["summary"]
        assert mock_engine.llm_client.chat_async.call_count == 5


class TestReactEngineToolCalls:

    @pytest.mark.asyncio
    async def test_single_tool_call_then_complete(self, mock_engine):
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(
                tool_calls=[_make_tool_call("call_1", "write_file", '{"path": "test.txt", "content": "hello"}')]
            ),
            _make_response(content="文件已创建"),
        ]

        result = await mock_engine.run("创建文件")

        assert result["success"] is True
        assert result["answer"] == "文件已创建"
        assert result["num_turns"] == 2

    @pytest.mark.asyncio
    async def test_multiple_iterations(self, mock_engine):
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 5:
                return _make_response(
                    tool_calls=[_make_tool_call(f"call_{call_count}", "read_file", f'{{"path": "file_{call_count}.txt"}}')]
                )
            else:
                return _make_response(content="所有文件已处理")

        mock_engine.llm_client.chat_async.side_effect = side_effect

        result = await mock_engine.run("处理文件")

        assert result["success"] is True
        assert result["num_turns"] == 5
        assert result["answer"] == "所有文件已处理"

    @pytest.mark.asyncio
    async def test_different_calls_reset_repeat_counter(self, mock_engine):
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(tool_calls=[_make_tool_call("c1", "read_file", '{"path": "a.txt"}')]),
            _make_response(tool_calls=[_make_tool_call("c2", "read_file", '{"path": "b.txt"}')]),
            _make_response(tool_calls=[_make_tool_call("c3", "read_file", '{"path": "c.txt"}')]),
            _make_response(tool_calls=[_make_tool_call("c4", "read_file", '{"path": "d.txt"}')]),
            _make_response(content="全部读取完成"),
        ]

        result = await mock_engine.run("读取文件")

        assert result["success"] is True
        assert result["num_turns"] == 5


class TestReactEngineContext:

    @pytest.mark.asyncio
    async def test_clears_memory_on_run(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        await mock_engine.run("测试任务")

        assert mock_engine.memory.clear_memory.call_count == 1

    @pytest.mark.asyncio
    async def test_adds_task_to_context(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(content="完成")

        await mock_engine.run("测试任务")

        mock_engine.context.add_context.assert_called_once_with("用户任务: 测试任务")


class TestReactEngineIterSteps:

    @pytest.mark.asyncio
    async def test_iter_steps_yields_events(self, mock_engine):
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(
                tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')]
            ),
            _make_response(content="任务完成"),
        ]

        events = []
        async for event in mock_engine.iter_steps("测试任务", max_tokens=10000, max_consecutive_repeats=5):
            events.append(event)

        types = [e["type"] for e in events]
        assert types == ["thought", "action", "observation", "thought", "answer"]

    @pytest.mark.asyncio
    async def test_iter_steps_token_limit_stops(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')],
            total_tokens=10000,
        )

        events = []
        async for event in mock_engine.iter_steps("测试任务", max_tokens=5000, max_consecutive_repeats=10):
            events.append(event)

        types = [e["type"] for e in events]
        assert types == ["thought", "action", "observation", "answer"]
        assert "安全网触发" in events[-1]["data"]["answer"]

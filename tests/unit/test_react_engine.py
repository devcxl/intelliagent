#!/usr/bin/env python3
"""
ReAct 循环引擎单元测试 — function calling 模式 + 双层安全网
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.context_manager import ContextManager
from src.core.react_engine import ReactEngine
from src.llm.llm_client import LLMResponse


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
        mock_engine.llm_client.chat_async.return_value = _make_response(content="任务已完成，答案是 42")

        result = await mock_engine.run("测试任务")

        assert result["success"] is True
        assert result["answer"] == "任务已完成，答案是 42"
        assert result["num_turns"] == 1
        assert "total_tokens" in result
        assert "prompt_tokens" in result
        assert "completion_tokens" in result
        assert "cached_tokens" in result

    @pytest.mark.asyncio
    async def test_counts_usage_from_llm_response(self, mock_engine):
        usage = SimpleNamespace(
            total_tokens=120,
            prompt_tokens=90,
            completion_tokens=30,
            prompt_tokens_details=SimpleNamespace(cached_tokens=12),
        )
        mock_engine.llm_client.chat_async.return_value = LLMResponse(
            content="完成",
            tool_calls=[],
            usage=usage,
        )

        result = await mock_engine.run("测试任务")

        assert result["total_tokens"] == 120
        assert result["prompt_tokens"] == 90
        assert result["completion_tokens"] == 30
        assert result["cached_tokens"] == 12

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

    @pytest.mark.asyncio
    async def test_max_iterations_stops_before_extra_llm_call(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "same.txt"}')],
            total_tokens=10,
        )

        result = await mock_engine.run("测试任务", max_iterations=2)

        assert result["success"] is False
        assert "最大轮数" in result["summary"]
        assert mock_engine.llm_client.chat_async.call_count == 2


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
                tc = _make_tool_call(
                    f"call_{call_count}",
                    "read_file",
                    f'{{"path": "file_{call_count}.txt"}}',
                )
                return _make_response(tool_calls=[tc])
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

    @pytest.mark.asyncio
    async def test_compacts_context_before_llm_call(self):
        llm = AsyncMock()
        llm.chat_async.return_value = _make_response(content="完成")
        ctx = ContextManager(
            system_prompt="system prompt",
            agent_prompt="agent prompt",
            tools_instruction="tools instruction",
            max_tokens=80,
        )
        engine = ReactEngine(
            llm_client=llm,
            context_manager=ctx,
            max_tokens=80,
        )

        await engine.run("当前任务" + "x" * 120)

        messages = llm.chat_async.call_args.kwargs["messages"]
        assert messages[:3] == [
            {"role": "system", "content": "system prompt"},
            {"role": "system", "content": "agent prompt"},
            {"role": "system", "content": "tools instruction"},
        ]
        assert len(messages) == 4
        assert messages[3]["role"] == "user"
        assert messages[3]["content"].startswith("以下是已压缩的上下文摘要")
        assert "当前任务" in messages[3]["content"]


class TestReactEngineIterSteps:
    @pytest.mark.asyncio
    async def test_iter_steps_yields_events(self, mock_engine):
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')]),
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

    @pytest.mark.asyncio
    async def test_iter_steps_max_iterations_reports_limit_iteration(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')],
            total_tokens=10,
        )

        events = []
        async for event in mock_engine.iter_steps("测试任务", max_iterations=1):
            events.append(event)

        assert [e["type"] for e in events] == ["thought", "action", "observation", "answer"]
        assert events[-1]["iteration"] == 1
        assert "最大轮数" in events[-1]["data"]["answer"]

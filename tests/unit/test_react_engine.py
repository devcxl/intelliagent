#!/usr/bin/env python3
"""ReactEngine 单元测试 — demo.py 风格的消息直挂 + compact_context。"""

from unittest.mock import AsyncMock, Mock

import pytest

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

    engine = ReactEngine(
        llm_client=llm,
        memory=memory,
        context_limit=10000,
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
        from types import SimpleNamespace

        usage = SimpleNamespace(
            total_tokens=120,
            prompt_tokens=90,
            completion_tokens=30,
            prompt_tokens_details=SimpleNamespace(cached_tokens=12),
        )
        from src.llm.llm_client import LLMResponse

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
    async def test_max_steps_triggers_safety_net(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')],
            total_tokens=10,
        )

        result = await mock_engine.run("测试任务", max_steps=3)

        assert result["success"] is False
        assert "安全网触发" in result["summary"]
        assert mock_engine.llm_client.chat_async.call_count == 3


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


class TestReactEngineMemory:
    @pytest.mark.asyncio
    async def test_adds_observation_on_tool_call(self, mock_engine):
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(tool_calls=[_make_tool_call("c1", "read_file", '{"path": "a.txt"}')]),
            _make_response(content="完成"),
        ]

        await mock_engine.run("读取文件")

        assert mock_engine.memory.add_observation.call_count == 1
        obs = mock_engine.memory.add_observation.call_args[0][0]
        assert obs["tool_name"] == "read_file"


class TestReactEngineIterSteps:
    @pytest.mark.asyncio
    async def test_iter_steps_yields_events(self, mock_engine):
        mock_engine.llm_client.chat_async.side_effect = [
            _make_response(tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')]),
            _make_response(content="任务完成"),
        ]

        events = []
        async for event in mock_engine.iter_steps("测试任务"):
            events.append(event)

        types = [e["type"] for e in events]
        assert types == ["thought", "action", "observation", "answer"]

    @pytest.mark.asyncio
    async def test_iter_steps_max_steps(self, mock_engine):
        mock_engine.llm_client.chat_async.return_value = _make_response(
            tool_calls=[_make_tool_call("call_1", "read_file", '{"path": "test.txt"}')],
            total_tokens=10,
        )

        events = []
        async for event in mock_engine.iter_steps("测试任务", max_steps=1):
            events.append(event)

        assert [e["type"] for e in events] == ["thought", "action", "observation", "answer"]

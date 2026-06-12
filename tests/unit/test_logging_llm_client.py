#!/usr/bin/env python3
"""
LLMClient.chat() DEBUG 日志测试

使用 caplog fixture 验证 DEBUG 级别日志输出。
"""
import logging
from types import SimpleNamespace

import src.llm.llm_client as llm_module
from src.llm.llm_client import LLMClient


class TestLLMClientChatDebugLogs:

    def test_chat_start_logs_model_msg_count_tool_count(self, monkeypatch, caplog):
        """chat() 调用开始时输出 model/msg_count/tool_count"""
        usage = SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10)
        message = SimpleNamespace(content="ok", tool_calls=None)

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=message)],
                    usage=usage,
                )

        class FakeOpenAI:
            def __init__(self, api_key=None, base_url=None):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)

        client = LLMClient(api_key="test-key", model="gpt-4o-mini")
        messages = [{"role": "user", "content": "hi"}]
        tools = [{"type": "function", "function": {"name": "read_file"}}]

        logging.getLogger("intelliagent").setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG)
        client.chat(messages=messages, tools=tools)

        assert "LLMClient - 调用开始" in caplog.text
        assert "model=gpt-4o-mini" in caplog.text
        assert "msg_count=1" in caplog.text
        assert "tool_count=1" in caplog.text

    def test_chat_success_logs_token_details(self, monkeypatch, caplog):
        """响应成功后输出 prompt_tokens/completion_tokens/total_tokens/has_tool_calls"""
        usage = SimpleNamespace(
            prompt_tokens=80,
            completion_tokens=20,
            total_tokens=100,
        )
        message = SimpleNamespace(content="完成", tool_calls=["tool-call"])

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=message)],
                    usage=usage,
                )

        class FakeOpenAI:
            def __init__(self, api_key=None, base_url=None):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)

        client = LLMClient(api_key="test-key")
        messages = [{"role": "user", "content": "hi"}]

        logging.getLogger("intelliagent").setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG)
        client.chat(messages=messages)

        assert "LLMClient - 调用成功" in caplog.text
        assert "prompt_tokens=80" in caplog.text
        assert "completion_tokens=20" in caplog.text
        assert "total_tokens=100" in caplog.text
        assert "has_tool_calls=True" in caplog.text

    def test_chat_success_logs_has_tool_calls_false_when_no_tool_calls(self, monkeypatch, caplog):
        """无 tool_calls 时 has_tool_calls=False"""
        usage = SimpleNamespace(
            prompt_tokens=50,
            completion_tokens=30,
            total_tokens=80,
        )
        message = SimpleNamespace(content="完成", tool_calls=None)

        class FakeCompletions:
            def create(self, **kwargs):
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=message)],
                    usage=usage,
                )

        class FakeOpenAI:
            def __init__(self, api_key=None, base_url=None):
                self.chat = SimpleNamespace(completions=FakeCompletions())

        monkeypatch.setattr(llm_module, "OpenAI", FakeOpenAI)

        client = LLMClient(api_key="test-key")
        messages = [{"role": "user", "content": "hi"}]

        logging.getLogger("intelliagent").setLevel(logging.DEBUG)
        caplog.set_level(logging.DEBUG)
        client.chat(messages=messages)

        assert "has_tool_calls=False" in caplog.text

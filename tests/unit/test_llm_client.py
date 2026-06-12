from __future__ import annotations

from types import SimpleNamespace

import src.llm.llm_client as llm_module
from src.llm.llm_client import LLMClient


def test_chat_preserves_usage_from_openai_response(monkeypatch):
    usage = SimpleNamespace(total_tokens=17)
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
    response = client.chat(messages=[{"role": "user", "content": "hi"}])

    assert response.content == "完成"
    assert response.tool_calls == ["tool-call"]
    assert response.usage is usage

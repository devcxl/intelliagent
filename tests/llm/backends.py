"""fake/real 双路径后端：同一测试组在录制传输与真实 litellm 调用上各跑一遍。

- fake 路径：monkeypatch litellm 入口（litellm.completion），重放录制 chunk 序列。
- real 路径：走真实 litellm 调用（openai/gpt-4o-mini），缺 OPENAI_API_KEY 时 skip。
"""

from __future__ import annotations

from dataclasses import dataclass

from src.llm.litellm_client import LiteLLMClient
from src.llm.stream import StreamRequest
from tests.llm.recorded import (
    EXPECTED_TOOL_NAME,
    FAKE_MODEL,
    REAL_MODEL,
    WEATHER_TOOL,
    Recorder,
    finish_chunk,
    text_chunk,
    tool_chunk,
    usage,
)


@dataclass
class FakeBackend:
    """录制传输后端：每个场景请求前先录制对应的 chunk 序列。"""

    recorder: Recorder
    client: LiteLLMClient

    def text_request(self) -> StreamRequest:
        self.recorder.record(
            [text_chunk("hel"), text_chunk("lo "), text_chunk("world"), finish_chunk("stop", usage(10, 5, 15))]
        )
        return StreamRequest(model=FAKE_MODEL, messages=[{"role": "user", "content": "hi"}])

    def tool_request(self) -> StreamRequest:
        self.recorder.record(
            [
                tool_chunk(index=0, id="call_1", name=EXPECTED_TOOL_NAME, arguments='{"city": '),
                tool_chunk(index=0, arguments='"Paris"}'),
                finish_chunk("tool_calls", usage(10, 5, 15)),
            ]
        )
        return StreamRequest(model=FAKE_MODEL, messages=[{"role": "user", "content": "天气如何"}], tools=[WEATHER_TOOL])

    def length_request(self) -> StreamRequest:
        self.recorder.record([text_chunk("partial answer"), finish_chunk("length", usage(10, 5, 15))])
        return StreamRequest(model=FAKE_MODEL, messages=[{"role": "user", "content": "hi"}], max_tokens=1)


@dataclass
class RealBackend:
    """真实 litellm 后端：构造确定性尽量高的真实请求。"""

    client: LiteLLMClient

    def text_request(self) -> StreamRequest:
        return StreamRequest(
            model=REAL_MODEL,
            messages=[{"role": "user", "content": "Reply with exactly one word: hello"}],
            temperature=0.0,
        )

    def tool_request(self) -> StreamRequest:
        return StreamRequest(
            model=REAL_MODEL,
            messages=[
                {"role": "user", "content": "Call the get_weather function for the city Paris. Do not reply with text."}
            ],
            tools=[WEATHER_TOOL],
            temperature=0.0,
        )

    def length_request(self) -> StreamRequest:
        return StreamRequest(
            model=REAL_MODEL,
            messages=[{"role": "user", "content": "Write a long essay about the ocean."}],
            max_tokens=1,
            temperature=0.0,
        )


Backend = FakeBackend | RealBackend

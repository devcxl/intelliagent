"""录制型传输基建：重放 litellm 形状的 chunk 序列或录制的异常。

chunk 用 litellm 的真实类型（ModelResponseStream/StreamingChoices/Delta）构造，
保证 fake 路径与真实调用路径的 chunk 形状一致，避免测试自造形状掩盖适配缺陷。
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from litellm.types.utils import ChatCompletionDeltaToolCall, Delta, ModelResponseStream, StreamingChoices
from litellm.types.utils import Usage as LiteLLMUsage

FAKE_MODEL = "deepseek/deepseek-chat"
REAL_MODEL = "openai/gpt-4o-mini"
EXPECTED_TEXT = "hello"
EXPECTED_TOOL_NAME = "get_weather"

WEATHER_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": EXPECTED_TOOL_NAME,
        "description": "Get the weather for a city",
        "parameters": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
            "required": ["city"],
        },
    },
}


def usage(prompt_tokens: int, completion_tokens: int, total_tokens: int) -> LiteLLMUsage:
    """构造 litellm 的 usage 对象。"""
    return LiteLLMUsage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens, total_tokens=total_tokens)


def text_chunk(text: str) -> ModelResponseStream:
    """构造一个文本增量 chunk。"""
    return _chunk(Delta(content=text))


def tool_chunk(
    index: int = 0,
    id: str | None = None,
    name: str | None = None,
    arguments: str = "",
) -> ModelResponseStream:
    """构造一个工具调用增量 chunk（id/name 只在首个增量出现）。"""
    function = {"name": name, "arguments": arguments}
    return _chunk(Delta(tool_calls=[ChatCompletionDeltaToolCall(index=index, id=id, function=function)]))


def finish_chunk(finish_reason: str | None, usage: LiteLLMUsage | None = None) -> ModelResponseStream:
    """构造收尾 chunk，可携带 usage。"""
    return _chunk(Delta(), finish_reason=finish_reason, usage=usage)


def usage_only_chunk(usage: LiteLLMUsage) -> ModelResponseStream:
    """构造 OpenAI include_usage 风格的 usage-only chunk（choices 为空）。"""
    return ModelResponseStream(choices=[], object="chat.completion.chunk", usage=usage)


def _chunk(delta: Delta, finish_reason: str | None = None, usage: LiteLLMUsage | None = None) -> ModelResponseStream:
    extra: dict[str, Any] = {}
    if usage is not None:
        extra["usage"] = usage
    return ModelResponseStream(
        choices=[StreamingChoices(index=0, delta=delta, finish_reason=finish_reason)],
        object="chat.completion.chunk",
        **extra,
    )


@dataclass
class Recorder:
    """录制型传输：按录制顺序重放 chunk 序列或抛出录制的异常。

    每条录制（episode）对应一次模型调用：list[chunk] 为一段流，BaseException 为该次调用直接失败。
    """

    episodes: list[list[Any] | Iterator[Any] | BaseException] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)

    def record(self, episode: list[Any] | Iterator[Any] | BaseException) -> None:
        """录制一次调用的结果：chunk 序列、异常或惰性流。"""
        self.episodes.append(episode)

    def completion(self, **kwargs: Any) -> Iterator[Any]:
        """替换 litellm.completion 入口：记录调用参数并重放下一条录制。"""
        self.calls.append(kwargs)
        if not self.episodes:
            raise AssertionError("录制脚本已耗尽：fake 传输收到额外的模型调用")
        episode = self.episodes.pop(0)
        if isinstance(episode, BaseException):
            raise episode
        return iter(episode)

    def sleep(self, seconds: float) -> None:
        """替换退避等待：只记录延迟，不真正等待。"""
        self.sleeps.append(seconds)

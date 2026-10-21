"""超时与重试测试（录制传输）：有限次数、指数退避、错误进流而非同步抛出。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from litellm.exceptions import BadRequestError, RateLimitError
from litellm.exceptions import Timeout as LiteLLMTimeout

from src.llm.litellm_client import LiteLLMClient
from src.llm.stream import Done, Error, StreamRequest, TextDelta, Usage
from tests.llm.recorded import FAKE_MODEL, Recorder, finish_chunk, text_chunk, usage


def _request() -> StreamRequest:
    return StreamRequest(model=FAKE_MODEL, messages=[{"role": "user", "content": "hi"}])


def test_timeout_retries_then_succeeds(recorder: Recorder, client: LiteLLMClient) -> None:
    recorder.record(TimeoutError("connect timed out"))
    recorder.record([text_chunk("ok"), finish_chunk("stop", usage(10, 5, 15))])

    events = list(client.stream(_request()))

    assert events == [TextDelta("ok"), Done("stop", Usage(10, 5, 15))]
    assert len(recorder.calls) == 2
    assert recorder.sleeps == [1.0]


def test_litellm_transient_errors_retry_with_growing_backoff(recorder: Recorder, client: LiteLLMClient) -> None:
    recorder.record(LiteLLMTimeout(message="t", model="m", llm_provider="p"))
    recorder.record(RateLimitError(message="r", model="m", llm_provider="p"))
    recorder.record([finish_chunk("stop", usage(1, 1, 2))])

    events = list(client.stream(_request()))

    assert isinstance(events[-1], Done)
    assert events[-1].stop_reason == "stop"
    assert len(recorder.calls) == 3
    assert recorder.sleeps == [1.0, 2.0]


def test_retries_exhausted_emits_error_event(recorder: Recorder, client: LiteLLMClient) -> None:
    for _ in range(3):
        recorder.record(TimeoutError("boom"))

    events = list(client.stream(_request()))

    assert events == [Error("TimeoutError: boom"), Done("error", None)]
    assert len(recorder.calls) == 3
    assert recorder.sleeps == [1.0, 2.0]


def test_non_retryable_error_fails_fast(recorder: Recorder, client: LiteLLMClient) -> None:
    recorder.record(BadRequestError(message="bad request", model="m", llm_provider="p"))

    events = list(client.stream(_request()))

    assert isinstance(events[0], Error) and events[0].message.startswith("BadRequestError")
    assert events[1] == Done("error", None)
    assert len(recorder.calls) == 1
    assert recorder.sleeps == []


def test_error_after_partial_stream_is_not_retried(recorder: Recorder, client: LiteLLMClient) -> None:
    def flaky_stream() -> Iterator[Any]:
        yield text_chunk("partial")
        raise ConnectionError("stream dropped")

    recorder.record(flaky_stream())

    events = list(client.stream(_request()))

    assert events == [TextDelta("partial"), Error("ConnectionError: stream dropped"), Done("error", None)]
    assert len(recorder.calls) == 1
    assert recorder.sleeps == []


def test_request_timeout_forwarded_to_litellm(recorder: Recorder) -> None:
    client = LiteLLMClient(request_timeout=30.0, sleep=recorder.sleep)
    recorder.record([finish_chunk("stop", usage(1, 1, 2))])

    list(client.stream(_request()))

    assert recorder.calls[0]["timeout"] == 30.0


def test_retry_budget_is_finite(recorder: Recorder) -> None:
    client = LiteLLMClient(max_retries=0, sleep=recorder.sleep)
    recorder.record(TimeoutError("boom"))

    events = list(client.stream(_request()))

    assert events == [Error("TimeoutError: boom"), Done("error", None)]
    assert len(recorder.calls) == 1
    assert recorder.sleeps == []


@pytest.mark.integration
class TestRealPathRetryContract:
    """重试/超时的真实路径契约（PR #68 审查 Spec 轴 high）：确定性故障注入 + 真实 litellm 调用。

    显式 opt-in（integration marker + OPENAI_API_KEY），默认测试集不触网。
    """

    def test_transient_error_then_real_call_recovers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("需要 OPENAI_API_KEY 环境变量（真实 litellm 路径）")

        import litellm

        real_completion = litellm.completion
        calls = {"n": 0}

        def fail_once_then_real(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RateLimitError(message="injected", model=kwargs["model"], llm_provider="openai")
            return real_completion(**kwargs)

        monkeypatch.setattr(litellm, "completion", fail_once_then_real)
        client = LiteLLMClient()
        events = list(
            client.stream(StreamRequest(model="openai/gpt-4o-mini", messages=[{"role": "user", "content": "hi"}]))
        )
        assert calls["n"] == 2  # 故障一次 + 真实重试一次
        assert isinstance(events[-1], Done) and events[-1].stop_reason == "stop"
        assert client.usage_log  # 真实 usage 落账

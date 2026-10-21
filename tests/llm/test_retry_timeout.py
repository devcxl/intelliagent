"""超时与重试测试（录制传输）：有限次数、指数退避、错误进流而非同步抛出。"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from litellm.exceptions import RateLimitError
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
    recorder.record(ValueError("bad request"))

    events = list(client.stream(_request()))

    assert events == [Error("ValueError: bad request"), Done("error", None)]
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

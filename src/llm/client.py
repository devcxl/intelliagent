"""传输无关的 LLM 编排层：重试、abort、usage 账本与错误进流（pi 两条纪律）。

照搬 pi 的两条纪律（docs/pi-engine-principles.md §7）：错误进流而非同步抛出、usage 逐响应落账。
协议差异全部由注入的 ProtocolAdapter 承担——编排层不感知 provider、端点或协议细节。

重试纪律：只在首个流事件前重试可重试错误；已产出增量的流不重试（重放会重复发给消费者）。
编程错误（TypeError/AttributeError 等）不属于 ProviderError，必须原样抛出。
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator

from src.llm.errors import ProviderError
from src.llm.protocols.base import ProtocolAdapter
from src.llm.stream import Done, Error, LLMEvent, StreamRequest, Usage, abort_requested


class ProviderClient:
    """LLM 编排层：消费适配器事件并落实重试、abort 与 usage 账本。

    Attributes:
        usage_log: 逐响应落账的 token 用量（每个正常完成或中止的响应一条）。
    """

    def __init__(
        self,
        adapter: ProtocolAdapter,
        *,
        request_timeout: float = 60.0,
        max_retries: int = 2,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """初始化编排层。

        Args:
            adapter: 协议适配器（唯一传输依赖）。
            request_timeout: 单次模型调用的超时（秒），每次尝试透传给适配器。
            max_retries: 瞬时错误的最大重试次数（总尝试次数 = max_retries + 1，不做无限重试）。
            backoff_base_seconds: 退避基数（秒），第 n 次重试前等待 backoff_base * 2**n。
            sleep: 退避等待函数，测试中注入以记录延迟而不真正等待。
        """
        self._adapter = adapter
        self._request_timeout = request_timeout
        self._max_retries = max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep
        self.usage_log: list[Usage] = []

    def stream(self, request: StreamRequest, *, abort: threading.Event | None = None) -> Iterator[LLMEvent]:
        """产出一次模型响应的流式事件序列，每条流以恰好一个 Done 结束。"""
        yield from self._stream_with_retries(request, abort)

    def _stream_with_retries(self, request: StreamRequest, abort: threading.Event | None) -> Iterator[LLMEvent]:
        failed_attempts = 0
        while True:
            if abort_requested(abort):
                yield Done(stop_reason="aborted", usage=None)
                return
            emitted = False
            try:
                for event in self._adapter.stream(request, abort, timeout=self._request_timeout):
                    emitted = True
                    if isinstance(event, Done) and event.usage is not None:
                        self.usage_log.append(event.usage)
                    yield event
                return
            except ProviderError as exc:
                if not emitted and failed_attempts < self._max_retries and exc.retryable:
                    self._sleep(self._backoff_base_seconds * (2**failed_attempts))
                    failed_attempts += 1
                    continue
                yield Error(message=str(exc))
                yield Done(stop_reason="error", usage=None)
                return

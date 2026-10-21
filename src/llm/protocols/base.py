"""LLM 协议适配器契约：只做请求投影、流事件翻译与错误分类。

编排层（src.llm.client）负责重试、abort、usage 账本与错误进流；适配器不重试、不记账。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Protocol

from src.llm.provider_registry import ModelTarget
from src.llm.stream import LLMEvent, StreamRequest


class ProtocolAdapter(Protocol):
    """一个线协议的流式实现：产出统一流事件，每条流以恰好一个 Done 结束。"""

    def stream(
        self, target: ModelTarget, request: StreamRequest, abort: threading.Event | None = None, *, timeout: float
    ) -> Iterator[LLMEvent]:
        """产出一次模型响应的流式事件序列。

        Args:
            target: 解析后的模型目标（协议、端点、密钥、限额）。
            request: 模型请求。
            abort: 中止信号；置位后以 Done(stop_reason="aborted") 收束并释放连接。
            timeout: 单次调用的超时（秒），由编排层传入。

        Returns:
            流式事件迭代器：text/toolcall 增量在前，Done 收尾（出错时 Error 先于 Done）。
        """
        ...

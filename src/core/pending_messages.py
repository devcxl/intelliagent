"""steering / follow-up 的待注入消息队列（pi-engine-principles §1：PendingMessageQueue）。

steer() 的消息在下一次请求组装前注入（运行中插话），follow_up() 的消息在 agent 即将停止时注入；
两者共用本队列，仅消费模式不同："all" 一次取空，"one-at-a-time" 每次只取最老一条。
"""

from __future__ import annotations

from collections import deque
from typing import Literal

QueueMode = Literal["all", "one-at-a-time"]
"""队列消费模式：全部注入 / 每次只注入最老一条（pi steeringMode、followUpMode）。"""


class PendingMessageQueue:
    """待注入消息队列：push 随时可调，drain 按消费模式取回。

    deque 的 append / popleft 是原子操作，drain 逐条弹出不丢并发 push 的消息。
    """

    def __init__(self, mode: QueueMode = "all") -> None:
        self._mode = mode
        self._messages: deque[str] = deque()

    def push(self, message: str) -> None:
        """入队一条待注入消息。"""
        self._messages.append(message)

    def drain(self) -> list[str]:
        """按消费模式取回待注入消息；队列为空返回空列表。

        popleft 是原子操作但"判空再弹"不是——并发 drain 用 try/except 兜住竞争，
        不丢并发 push 的消息（下一个 drain 会取到）。
        """
        if self._mode == "one-at-a-time":
            try:
                return [self._messages.popleft()]
            except IndexError:
                return []
        drained: list[str] = []
        while True:
            try:
                drained.append(self._messages.popleft())
            except IndexError:
                return drained

    def __bool__(self) -> bool:
        return bool(self._messages)

"""Provider 调用类错误：由协议适配器分类，编排层据此决定重试与错误进流。

编程错误（TypeError/AttributeError 等）不属于此类，必须原样抛出，不伪装成模型错误。
"""

from __future__ import annotations


class ProviderError(Exception):
    """一次 provider 调用的可诊断错误。

    Attributes:
        retryable: 是否属于瞬时错误，可在首个流事件前重试。
    """

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable

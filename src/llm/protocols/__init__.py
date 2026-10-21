"""协议适配器：每个线协议一个实现，统一产出 src.llm.stream 的流事件。"""

from src.llm.protocols.base import ProtocolAdapter

__all__ = ["ProtocolAdapter"]

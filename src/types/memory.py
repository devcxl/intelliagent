from __future__ import annotations

from typing import Any, Protocol


class MemoryProtocol(Protocol):
    def clear_memory(self) -> None: ...
    def add_observation(self, obs: dict[str, Any]) -> None: ...


__all__ = [
    "MemoryProtocol",
]

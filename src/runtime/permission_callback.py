from __future__ import annotations

import asyncio
import json
from typing import Any

from src.types.permission import PermissionCallback


class CliCallback(PermissionCallback):
    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout

    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, self._prompt, tool_name, args, reason),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            print(f"\n⏰ 确认超时（{self._timeout}s），自动拒绝")
            return False

    def _prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        args_str = json.dumps(args, ensure_ascii=False)
        print(f"\n⚠️  权限确认 [{tool_name}] {args_str}")
        print(f"   原因: {reason}")
        return input("   允许执行？[y/N] ").strip().lower() == "y"

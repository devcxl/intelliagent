from __future__ import annotations

import asyncio
import json
from typing import Any

from src.permission.types import PermissionCallback


class CliCallback(PermissionCallback):
    """CLI 交互式权限确认回调。

    在终端中向用户展示工具调用详情并等待 y/N 确认，
    超时后自动拒绝。
    """

    def __init__(self, timeout: float = 120.0) -> None:
        """初始化 CLI 权限回调。

        Args:
            timeout: 等待用户确认的超时秒数，默认 120 秒
        """
        self._timeout = timeout

    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        """异步权限确认入口，带超时控制。

        Args:
            tool_name: 待确认的工具名称
            args: 工具调用参数
            reason: 触发权限确认的原因

        Returns:
            True 表示用户同意执行，False 表示拒绝或超时
        """
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
        """在终端中展示权限确认信息并读取用户输入。

        Args:
            tool_name: 待确认的工具名称
            args: 工具调用参数（JSON 序列化后展示）
            reason: 触发权限确认的原因

        Returns:
            True 表示用户输入 y，False 表示其他输入
        """
        args_str = json.dumps(args, ensure_ascii=False)
        print(f"\n⚠️  权限确认 [{tool_name}] {args_str}")
        print(f"   原因: {reason}")
        return input("   允许执行？[y/N] ").strip().lower() == "y"

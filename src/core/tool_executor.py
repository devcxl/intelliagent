from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.permission import PermissionCallbackProtocol, PermissionEngineProtocol

if TYPE_CHECKING:
    from src.core.react_engine import ToolRegistryProtocol


@dataclass
class ToolExecutionResult:
    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]
    content: str
    status: str = "success"
    error: str | None = None


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistryProtocol,
        permission_engine: PermissionEngineProtocol | None = None,
        permission_callback: PermissionCallbackProtocol | None = None,
    ) -> None:
        self._registry = registry
        self._permission_engine = permission_engine
        self._permission_callback = permission_callback

    async def execute(self, tool_call: dict[str, Any]) -> ToolExecutionResult:
        tool_name = tool_call.get("function", {}).get("name", "")
        tool_call_id = tool_call.get("id", "")
        args_raw = tool_call.get("function", {}).get("arguments", "{}")

        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
        except json.JSONDecodeError:
            args = {}

        if self._permission_engine:
            decision = self._permission_engine.check(tool_name, args)
            if decision.action == "deny":
                return ToolExecutionResult(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    tool_args=args,
                    content=json.dumps(
                        {"status": "error", "error": f"权限拒绝: {decision.reason}"}, ensure_ascii=False
                    ),
                    status="denied",
                )
            if decision.action == "ask":
                if self._permission_callback:
                    approved = await self._permission_callback.on_prompt(tool_name, args, decision.reason)
                    if not approved:
                        return ToolExecutionResult(
                            tool_call_id=tool_call_id,
                            tool_name=tool_name,
                            tool_args=args,
                            content=json.dumps({"status": "error", "error": "用户拒绝执行"}, ensure_ascii=False),
                            status="rejected",
                        )
                else:
                    return ToolExecutionResult(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        tool_args=args,
                        content=json.dumps(
                            {"status": "error", "error": f"需要确认但无回调: {decision.reason}"},
                            ensure_ascii=False,
                        ),
                        status="no_callback",
                    )

        try:
            result = await self._registry.call_tool(tool_name=tool_name, **args)
        except Exception as e:
            return ToolExecutionResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                tool_args=args,
                content=json.dumps({"status": "error", "error": f"工具执行异常: {e}"}, ensure_ascii=False),
                status="error",
                error=str(e),
            )
        return ToolExecutionResult(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            tool_args=args,
            content=result,
        )


__all__ = ["ToolExecutor", "ToolExecutionResult"]

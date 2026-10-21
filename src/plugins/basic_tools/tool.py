"""Tool 能力形态：ToolSpec 是注册到 CapabilityKind.TOOL 的能力提供者（CONTEXT 术语：Tool）。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from src.plugins.basic_tools.result import tool_error

Handler = Callable[..., Awaitable[str]]


@dataclass(frozen=True)
class ToolSpec:
    """一个可被模型调用的工具：原生 JSON Schema 参数表 + 异步执行函数。

    parameters 是 JSON Schema 的 object schema（支持嵌套与 enum，不降级为扁平参数）；
    handler 接收与 properties 同名的关键字参数，返回 JSON 结果字符串。
    """

    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: Handler

    async def run(self, **kwargs: Any) -> str:
        """执行工具：参数不匹配或意外异常都收敛为错误信封，绝不裸抛到引擎。"""
        try:
            return await self.handler(**kwargs)
        except TypeError as exc:
            return tool_error("INVALID_ARGUMENT", f"工具 {self.name} 参数不合法: {exc}")
        except Exception as exc:
            return tool_error("EXECUTION_ERROR", f"工具 {self.name} 执行失败: {exc}")

"""核心模块 — ReAct 引擎、权限引擎、上下文管理、Token 估算、窗口策略。"""

from src.core.context_manager import (
    DEFAULT_AGENT_PROMPT,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_TOOLS_INSTRUCTION,
    ContextManager,
    ContextSnapshot,
    ContextSummary,
)
from src.core.permission_engine import PermissionEngine, load_permission_engine
from src.core.react_engine import ReactEngine
from src.core.window_strategies import SlidingWindowStrategy, WindowStrategy

__all__ = [
    "ReactEngine",
    "PermissionEngine",
    "load_permission_engine",
    "ContextManager",
    "ContextSnapshot",
    "ContextSummary",
    "WindowStrategy",
    "SlidingWindowStrategy",
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_AGENT_PROMPT",
    "DEFAULT_TOOLS_INSTRUCTION",
]

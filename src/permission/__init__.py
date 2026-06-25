"""权限模块 — 类型定义、权限引擎、权限回调。"""

from src.permission.callback import CliCallback
from src.permission.engine import PermissionEngine, load_permission_engine
from src.permission.types import (
    Decision,
    PermissionAction,
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)

__all__ = [
    "PermissionAction",
    "Decision",
    "PermissionCallbackProtocol",
    "PermissionEngineProtocol",
    "PermissionEngine",
    "load_permission_engine",
    "CliCallback",
]

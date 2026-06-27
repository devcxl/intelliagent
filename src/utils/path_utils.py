from __future__ import annotations

import os
from pathlib import Path


def resolve_workspace_root(workspace: str | Path | None = None) -> Path | None:
    """解析工作区根路径，优先取参数，其次取环境变量。

    Returns:
        解析后的 Path，均不可用时返回 None
    """
    if workspace:
        return Path(workspace).resolve()
    env_root = os.environ.get("INTELLIAGENT_WORKSPACE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return None


def is_path_in_workspace(path: str | Path, workspace: Path) -> bool:
    """检查路径是否在工作区范围内。

    空路径返回 True（无路径参数的工具视为不受限）。

    Args:
        path: 待检查路径（字符串或 Path，支持相对路径）
        workspace: 工作区根路径

    Returns:
        True 表示路径在工作区内
    """
    if not path:
        return True
    p = Path(path)
    if not p.is_absolute():
        p = workspace / p
    try:
        resolved = p.resolve()
        workspace_resolved = workspace.resolve()
        resolved.relative_to(workspace_resolved)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def is_in_external_directories(path: str | Path, external_directories: list[str]) -> bool:
    """检查路径是否在外部目录白名单中。

    Args:
        path: 待检查路径
        external_directories: 外部目录白名单列表

    Returns:
        True 表示路径在白名单中
    """
    if not path or not external_directories:
        return False
    resolved = Path(path).resolve()
    for d in external_directories:
        dir_resolved = Path(d).resolve()
        try:
            resolved.relative_to(dir_resolved)
            return True
        except ValueError:
            continue
    return False

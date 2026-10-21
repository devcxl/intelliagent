from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PathCheckResult:
    allowed_by_boundary: bool
    in_workspace: bool
    in_external_directory: bool
    resolved_path: Path | None = None
    reason: str = ""


@dataclass(frozen=True)
class PathPolicy:
    workspace: Path
    external_directories: tuple[Path, ...] = ()

    def check(self, path: str | Path) -> PathCheckResult:
        if not path:
            return PathCheckResult(
                allowed_by_boundary=True,
                in_workspace=True,
                in_external_directory=False,
                reason="空路径视为允许",
            )

        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p

        try:
            resolved = p.resolve()
            workspace_resolved = self.workspace.resolve()
            resolved.relative_to(workspace_resolved)
            return PathCheckResult(
                allowed_by_boundary=True,
                in_workspace=True,
                in_external_directory=False,
                resolved_path=resolved,
            )
        except (OSError, RuntimeError, ValueError):
            pass

        try:
            resolved = p.resolve()
            for d in self.external_directories:
                dir_resolved = d.resolve()
                resolved.relative_to(dir_resolved)
                return PathCheckResult(
                    allowed_by_boundary=True,
                    in_workspace=False,
                    in_external_directory=True,
                    resolved_path=resolved,
                )
        except (OSError, RuntimeError, ValueError):
            pass

        try:
            resolved = p.resolve()
        except (OSError, RuntimeError):
            return PathCheckResult(
                allowed_by_boundary=False,
                in_workspace=False,
                in_external_directory=False,
                reason=f"路径无法解析: {path}",
            )

        return PathCheckResult(
            allowed_by_boundary=False,
            in_workspace=False,
            in_external_directory=False,
            resolved_path=resolved,
            reason=f"路径不在工作区也不在外部目录白名单中: {resolved}",
        )


def resolve_workspace_root(workspace: str | Path | None = None) -> Path | None:
    """解析工作区根路径：优先取参数，其次取 INTELLIAGENT_WORKSPACE_ROOT 环境变量。

    Returns:
        解析后的 Path，均不可用时返回 None
    """
    if workspace:
        return Path(workspace).resolve()
    env_root = os.environ.get("INTELLIAGENT_WORKSPACE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return None


__all__ = ["PathCheckResult", "PathPolicy", "resolve_workspace_root"]

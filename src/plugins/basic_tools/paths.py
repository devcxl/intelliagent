"""工具路径处理：path 参数校验与工作区边界检查（复用 utils.PathPolicy 语义）。"""

from __future__ import annotations

from pathlib import Path

from src.plugins.basic_tools.result import tool_error
from src.utils.path_policy import PathPolicy, resolve_workspace_root


def resolve_tool_path(path: object, path_policy: PathPolicy | None) -> tuple[Path | None, str | None]:
    """校验并解析工具的 path 参数，做工作区边界检查。

    相对路径基于 CWD 解析；边界检查与文件操作使用同一解析结果，
    消除旧实现中"检查用一套路径、使用另一套路径"的不一致。
    未配置任何工作区根（显式 policy 或环境变量）时不做边界检查。

    Returns:
        (解析后的路径, None) 或 (None, 错误信封)。
    """
    if not isinstance(path, str) or not path.strip():
        return None, tool_error("EMPTY_PATH", "path 参数为空或非字符串类型")
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        return None, tool_error("PATH_RESOLVE_ERROR", f"无法解析路径: {path} ({exc})")

    policy = path_policy
    if policy is None:
        workspace = resolve_workspace_root()
        if workspace is not None:
            policy = PathPolicy(workspace=workspace)
    if policy is not None:
        check = policy.check(resolved)
        if not check.allowed_by_boundary:
            return None, tool_error(
                "PATH_OUTSIDE_WORKSPACE",
                f"路径超出工作区范围: {resolved} (工作区: {policy.workspace})",
            )
    return resolved, None

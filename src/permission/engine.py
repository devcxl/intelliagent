from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any, Sequence

from src.permission.types import Decision, PermissionAction
from src.utils.path_policy import PathPolicy

if TYPE_CHECKING:
    from src.config.unified_config import PermissionsConfig

# ---------------------------------------------------------------------------
# 默认规则（last-match-wins，列表末尾优先级最高）
# ---------------------------------------------------------------------------

_DEFAULT_RULES: tuple[tuple[str, str], ...] = (
    ("*", "ask"),
    ("read *", "allow"),
    (".env*", "deny"),
    ("skill *", "allow"),
    ("mcp *", "allow"),
    ("edit *", "ask"),
    ("bash *", "ask"),
    ("write *", "ask"),
)


def _match_rule(pattern: str, tool_name: str, args: dict[str, Any]) -> bool:
    """检查 pattern 是否匹配工具名或参数值。

    工具名匹配时将 pattern 中空格压缩（"read *" → "read*"），
    参数值匹配时使用原始 pattern。
    """
    compact = pattern.replace(" ", "")
    if fnmatch.fnmatch(tool_name, compact):
        return True
    for value in args.values():
        if isinstance(value, str) and fnmatch.fnmatch(value, pattern):
            return True
    return False


def _evaluate_rules(rules: Sequence[tuple[str, str]], tool_name: str, args: dict[str, Any]) -> Decision | None:
    """last-match-wins 遍历规则列表，返回最后匹配的决策。"""
    last_match: tuple[str, str] | None = None
    for pattern, action in rules:
        if _match_rule(pattern, tool_name, args):
            last_match = (pattern, action)
    if last_match is None:
        return None
    pattern, action = last_match
    return Decision(
        action=PermissionAction(action),
        reason=f"匹配规则: pattern={pattern}, action={action}",
    )


class PermissionEngine:
    """权限引擎 — last-match-wins + fnmatch 模式匹配。

    构造函数：
        rules: list[tuple[str, str]] — 用户配置的 (pattern, action) 规则列表
        workspace: Path — 工作区根路径
        external_directories: list[str] | None — 外部目录白名单
    """

    _DEFAULT_RULES: tuple[tuple[str, str], ...] = _DEFAULT_RULES

    def __init__(
        self,
        rules: list[tuple[str, str]],
        workspace: Path,
        external_directories: list[str] | None = None,
    ) -> None:
        self._rules = rules
        self._path_policy = PathPolicy(
            workspace=workspace,
            external_directories=tuple(Path(d) for d in (external_directories or [])),
        )

    @property
    def rules(self) -> list[tuple[str, str]]:
        """获取当前规则列表。"""
        return self._rules

    def check(self, tool_name: str, args: dict[str, Any]) -> Decision:
        """检查工具调用是否被允许。

        优先级：用户规则（last-match-wins）> 安全检查（路径越界）> 默认规则 > 绝对兜底。

        Args:
            tool_name: 工具名称
            args: 工具参数字典

        Returns:
            权限决策结果
        """
        # 1. 用户规则优先（last-match-wins），用户可以覆盖任何行为
        result = _evaluate_rules(self._rules, tool_name, args)
        if result is not None:
            return result

        # 2. 安全检查：外部路径不在白名单中 → deny
        path = args.get("path", "")
        if isinstance(path, str) and path:
            pc = self._path_policy.check(path)
            if not pc.allowed_by_boundary:
                return Decision(
                    action=PermissionAction.deny,
                    reason=f"路径不在工作区且不在外部目录白名单中: {path}",
                )
            if not pc.in_workspace and pc.in_external_directory:
                return Decision(
                    action=PermissionAction.ask,
                    reason=f"外部目录路径需确认: {path}",
                )

        # 3. 默认规则（last-match-wins）
        result = _evaluate_rules(self._DEFAULT_RULES, tool_name, args)
        if result is not None:
            return result

        # 4. 绝对兜底
        return Decision(action=PermissionAction.ask, reason="无匹配权限规则，默认需要确认")


def load_permission_engine(
    config: PermissionsConfig,
    workspace: Path | None = None,
) -> PermissionEngine:
    """从 PermissionsConfig 对象加载权限引擎。

    Args:
        config: 权限配置对象
        workspace: 工作区根路径，默认使用当前工作目录

    Returns:
        配置好的 PermissionEngine 实例
    """
    rules = [(r.pattern, r.action) for r in config.rules]
    return PermissionEngine(
        rules=rules,
        workspace=workspace or Path.cwd(),
        external_directories=config.external_directories,
    )

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol

from src.types.permission import Decision, PermissionAction, Rule

_SHELL_DELIMITERS = re.compile(r"[;&|\n]")
_CMD_SUBSTITUTION = re.compile(r"\$\(|`")
_REDIRECT_DANGER = re.compile(r">[>\s]")
_XARGS_DANGER = re.compile(r"\bxargs\s+(rm|mv|dd|chmod|chown)\b")
_SUDO_PATTERN = re.compile(r"\b(sudo|su)\b")

DANGEROUS_COMMANDS: set[str] = {
    "rm",
    "mv",
    "dd",
    "mkfs",
    "mkswap",
    "swapon",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "chmod",
    "chown",
    "chgrp",
    "kill",
    "pkill",
    "killall",
    "fdisk",
    "parted",
    "wipefs",
    "iptables",
    "nft",
    "ufw",
}

PATH_SENSITIVE_COMMANDS: set[str] = {
    "ln",
    "cp",
    "mv",
    "rsync",
    "curl",
    "wget",
    "scp",
    "find",
}

DEFAULT_RULES: list[dict[str, Any]] = [
    {"tool": "run_shell", "action": "prompt", "conditions": {"dangerous": True}},
    {"tool": "run_shell", "action": "prompt", "conditions": {"path_sensitive": True}},
    {"tool": "run_shell", "action": "allow", "conditions": {}},
    {"tool": "read_file", "action": "allow", "conditions": {"path_in_workspace": True}},
    {"tool": "read_file", "action": "prompt", "conditions": {"path_in_workspace": False}},
    {"tool": "write_file", "action": "allow", "conditions": {"path_in_workspace": True}},
    {"tool": "write_file", "action": "prompt", "conditions": {"path_in_workspace": False}},
    {"tool": "edit_file", "action": "allow", "conditions": {"path_in_workspace": True}},
    {"tool": "edit_file", "action": "prompt", "conditions": {"path_in_workspace": False}},
    {"tool": "todo_write", "action": "allow", "conditions": {}},
]


def _token_to_cmd(token: str) -> str:
    token = token.strip()
    if not token:
        return token
    while "=" in token and token.split("=", 1)[0].isidentifier():
        token = token.split("=", 1)[1].strip()
    return token.rsplit("/", 1)[-1] if "/" in token else token


def _is_dangerous_cmd(cmd_str: str) -> bool:
    if not cmd_str or not cmd_str.strip():
        return False

    if _CMD_SUBSTITUTION.search(cmd_str):
        return True
    if _REDIRECT_DANGER.search(cmd_str):
        return True
    if _XARGS_DANGER.search(cmd_str):
        return True
    if _SUDO_PATTERN.search(cmd_str):
        return True

    for segment in _SHELL_DELIMITERS.split(cmd_str):
        tokens = segment.strip().split()
        if tokens:
            cmd_name = _token_to_cmd(tokens[0])
            if cmd_name and cmd_name in DANGEROUS_COMMANDS:
                return True

    return False


def _is_path_sensitive(cmd_str: str) -> bool:
    tokens = cmd_str.strip().split()
    if not tokens:
        return False
    cmd_name = _token_to_cmd(tokens[0])
    if cmd_name not in PATH_SENSITIVE_COMMANDS:
        return False
    for token in tokens[1:]:
        if token.startswith("/"):
            return True
        if token.startswith("../"):
            return True
        if token.startswith("~"):
            return True
        if "/proc/" in token or "/dev/" in token:
            return True
    return False


def _is_path_in_workspace(path: str, workspace: Path) -> bool:
    if not path:
        return True
    resolved = Path(path).resolve()
    workspace_resolved = workspace.resolve()
    try:
        resolved.relative_to(workspace_resolved)
        return True
    except ValueError:
        return False


class ConditionStrategy(Protocol):
    """条件评估策略协议 — 每种条件类型对应一个实现。"""

    def evaluate(self, args: dict[str, Any], workspace: Path) -> bool: ...


class DangerousConditionStrategy:
    """危险命令条件策略 — 复用 _is_dangerous_cmd 逻辑。"""

    def evaluate(self, args: dict[str, Any], workspace: Path) -> bool:
        return _is_dangerous_cmd(args.get("cmd", ""))


class PathInWorkspaceConditionStrategy:
    """工作区路径条件策略 — 复用 _is_path_in_workspace 逻辑。"""

    def evaluate(self, args: dict[str, Any], workspace: Path) -> bool:
        return _is_path_in_workspace(args.get("path", ""), workspace)


class PathSensitiveConditionStrategy:
    """路径敏感命令条件策略 — 复用 _is_path_sensitive 逻辑。"""

    def evaluate(self, args: dict[str, Any], workspace: Path) -> bool:
        return _is_path_sensitive(args.get("cmd", ""))


_STRATEGIES: dict[str, ConditionStrategy] = {
    "dangerous": DangerousConditionStrategy(),
    "path_in_workspace": PathInWorkspaceConditionStrategy(),
    "path_sensitive": PathSensitiveConditionStrategy(),
}


class PermissionEngine:
    def __init__(self, rules: list[dict[str, Any]], workspace: Path | None = None) -> None:
        self._rules = [Rule(**r) for r in rules]
        self._workspace = workspace or Path.cwd()

    @property
    def rules(self) -> list[Rule]:
        return self._rules

    def check(self, tool_name: str, args: dict[str, Any]) -> Decision:
        for rule in self._rules:
            if rule.tool != tool_name and rule.tool != "*":
                continue
            if self._evaluate_condition(rule.conditions, args):
                return Decision(action=rule.action, reason=self._reason(rule))
        return Decision(action=PermissionAction.prompt, reason="无匹配权限规则，默认需要确认")

    def _evaluate_condition(self, conditions: dict[str, Any], args: dict[str, Any]) -> bool:
        if not conditions:
            return True
        for key, expected in conditions.items():
            strategy = _STRATEGIES.get(key)
            if strategy is None:
                return False
            actual = strategy.evaluate(args, self._workspace)
            if actual != expected:
                return False
        return True

    @staticmethod
    def _reason(rule: Rule) -> str:
        return f"匹配规则: tool={rule.tool}, action={rule.action.value}, conditions={rule.conditions}"


def load_permission_engine(config_path: str, workspace: Path | None = None) -> PermissionEngine:
    rules: list[dict[str, Any]]
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
            rules = data.get("rules", [])
    except (FileNotFoundError, json.JSONDecodeError):
        rules = DEFAULT_RULES
    if not rules:
        rules = DEFAULT_RULES
    return PermissionEngine(rules=rules, workspace=workspace)

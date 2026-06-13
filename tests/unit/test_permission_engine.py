from __future__ import annotations

from pathlib import Path

import pytest

from src.core.permission_engine import (
    PermissionEngine,
    _is_dangerous_cmd,
    _is_path_in_workspace,
    _is_path_sensitive,
    load_permission_engine,
)
from src.config.unified_config import PermissionsConfig, PermissionRule
from src.runtime.permission_callback import CliCallback

# ============================================================================
# 2.1 — PermissionEngine.check() 测试
# ============================================================================


def test_check_allow():
    engine = PermissionEngine(
        rules=[
            {"tool": "todo_write", "action": "allow", "conditions": {}},
        ]
    )
    d = engine.check("todo_write", {"todos": "[]"})
    assert d.action.value == "allow"


def test_check_deny():
    engine = PermissionEngine(
        rules=[
            {"tool": "run_shell", "action": "deny", "conditions": {"dangerous": True}},
        ]
    )
    d = engine.check("run_shell", {"cmd": "rm -rf /"})
    assert d.action.value == "deny"


def test_check_prompt():
    engine = PermissionEngine(
        rules=[
            {"tool": "read_file", "action": "prompt", "conditions": {"path_in_workspace": False}},
        ]
    )
    d = engine.check("read_file", {"path": "/etc/passwd"})
    assert d.action.value == "prompt"


def test_check_default_prompt_when_no_match():
    engine = PermissionEngine(rules=[])
    d = engine.check("unknown_tool", {})
    assert d.action.value == "prompt"
    assert "默认需要确认" in d.reason


def test_check_condition_mismatch_skips_rule():
    engine = PermissionEngine(
        rules=[
            {"tool": "read_file", "action": "deny", "conditions": {"path_in_workspace": False}},
            {"tool": "read_file", "action": "allow", "conditions": {"path_in_workspace": True}},
        ]
    )
    d = engine.check("read_file", {"path": str(Path.cwd() / "src" / "test.py")})
    assert d.action.value == "allow"


def test_check_rule_order_matters_first_match_wins():
    engine = PermissionEngine(
        rules=[
            {"tool": "run_shell", "action": "allow", "conditions": {}},
            {"tool": "run_shell", "action": "deny", "conditions": {"dangerous": True}},
        ]
    )
    d = engine.check("run_shell", {"cmd": "rm -rf /"})
    assert d.action.value == "allow"


def test_check_wildcard_tool():
    engine = PermissionEngine(
        rules=[
            {"tool": "*", "action": "deny", "conditions": {}},
        ]
    )
    d = engine.check("some_tool", {})
    assert d.action.value == "deny"


# ============================================================================
# 2.2 — _is_path_in_workspace 测试
# ============================================================================


def test_path_in_workspace():
    ws = Path("/tmp/test-ws")
    assert _is_path_in_workspace("/tmp/test-ws/src/foo.py", ws)


def test_path_outside_workspace():
    ws = Path("/tmp/test-ws")
    assert not _is_path_in_workspace("/etc/passwd", ws)


def test_path_traversal_blocked():
    ws = Path("/tmp/test-ws")
    assert not _is_path_in_workspace("/tmp/test-ws/../outside", ws)


def test_path_empty_defaults_true():
    ws = Path("/tmp/test-ws")
    assert _is_path_in_workspace("", ws)


def test_path_symlink_resolved():
    ws = Path("/tmp/test-ws")
    assert not _is_path_in_workspace("/proc/self/cwd", ws)


# ============================================================================
# 2.3 — _is_dangerous_cmd 测试
# ============================================================================


def test_dangerous_rm():
    assert _is_dangerous_cmd("rm -rf /")


def test_dangerous_ls_is_safe():
    assert not _is_dangerous_cmd("ls -la")


def test_dangerous_full_path_rm():
    assert _is_dangerous_cmd("/usr/bin/rm -rf /tmp/x")


def test_dangerous_pipe():
    assert _is_dangerous_cmd("ls | rm -rf /tmp/x")


def test_dangerous_semicolon():
    assert _is_dangerous_cmd("ls; rm -rf /tmp/x")


def test_dangerous_and():
    assert _is_dangerous_cmd("ls && rm -rf /")


def test_dangerous_cmd_substitution_dollar():
    assert _is_dangerous_cmd("echo $(rm -rf /)")


def test_dangerous_cmd_substitution_backtick():
    assert _is_dangerous_cmd("echo `rm -rf /`")


def test_dangerous_redirect():
    assert _is_dangerous_cmd("grep x > /etc/hosts")


def test_dangerous_xargs():
    assert _is_dangerous_cmd("find . | xargs rm")


def test_dangerous_sudo():
    assert _is_dangerous_cmd("sudo rm -rf /")


def test_dangerous_empty():
    assert not _is_dangerous_cmd("")


def test_dangerous_shutdown():
    assert _is_dangerous_cmd("shutdown now")


# ============================================================================
# 2.4 — _is_path_sensitive 测试
# ============================================================================


def test_path_sensitive_cp_absolute():
    assert _is_path_sensitive("cp /etc/passwd ./")


def test_path_sensitive_cp_relative_safe():
    assert not _is_path_sensitive("cp src/a src/b")


def test_path_sensitive_find_root():
    assert _is_path_sensitive("find / -name '*.conf'")


def test_path_sensitive_cp_traversal():
    assert _is_path_sensitive("cp ../outside ./inside")


def test_path_sensitive_cp_home():
    assert _is_path_sensitive("cp ~/.ssh/id_rsa ./")


def test_path_sensitive_cp_proc():
    assert _is_path_sensitive("cp /proc/self/environ ./")


def test_path_sensitive_non_sensitive_cmd():
    assert not _is_path_sensitive("cat /etc/passwd")


# ============================================================================
# 2.5 — CliCallback.on_prompt 测试
# ============================================================================


@pytest.mark.asyncio
async def test_callback_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    cb = CliCallback(timeout=10.0)
    result = await cb.on_prompt("test_tool", {"arg": "val"}, "test reason")
    assert result is True


@pytest.mark.asyncio
async def test_callback_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    cb = CliCallback(timeout=10.0)
    result = await cb.on_prompt("test_tool", {"arg": "val"}, "test reason")
    assert result is False


@pytest.mark.asyncio
async def test_callback_timeout(monkeypatch):
    def blocking_input(_prompt):
        import time

        time.sleep(2)
        return "y"

    monkeypatch.setattr("builtins.input", blocking_input)
    cb = CliCallback(timeout=0.5)
    result = await cb.on_prompt("test_tool", {}, "timeout test")
    assert result is False


@pytest.mark.asyncio
async def test_callback_uppercase_y(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "Y")
    cb = CliCallback(timeout=10.0)
    result = await cb.on_prompt("test_tool", {}, "uppercase y")
    assert result is True


# ============================================================================
# 2.7 — load_permission_engine 测试
# ============================================================================


def test_load_from_missing_file_uses_defaults():
    engine = load_permission_engine("/tmp/nonexistent_permissions.json")
    assert len(engine.rules) == 10
    d = engine.check("todo_write", {})
    assert d.action.value == "allow"


def test_load_from_valid_json(tmp_path):
    config = tmp_path / "permissions.json"
    config.write_text('{"rules": [{"tool": "run_shell", "action": "deny", "conditions": {}}]}')
    engine = load_permission_engine(str(config))
    assert len(engine.rules) == 1
    d = engine.check("run_shell", {"cmd": "ls"})
    assert d.action.value == "deny"


def test_load_from_empty_rules_uses_defaults(tmp_path):
    config = tmp_path / "permissions.json"
    config.write_text('{"rules": []}')
    engine = load_permission_engine(str(config))
    assert len(engine.rules) == 10


def test_load_broken_json_uses_defaults(tmp_path):
    config = tmp_path / "permissions.json"
    config.write_text("not json")
    engine = load_permission_engine(str(config))
    assert len(engine.rules) == 10


# ============================================================================
# 新增：load_permission_engine 接受 PermissionsConfig 对象
# ============================================================================


def test_load_from_permissions_config_object():
    """load_permission_engine 应接受 PermissionsConfig 对象。"""
    perms = PermissionsConfig(
        rules=[
            PermissionRule(tool="run_shell", action="deny", conditions={}),
            PermissionRule(tool="read_file", action="allow", conditions={"path_in_workspace": True}),
        ]
    )
    engine = load_permission_engine(perms)
    assert len(engine.rules) == 2
    d = engine.check("run_shell", {"cmd": "ls"})
    assert d.action.value == "deny"


def test_load_from_permissions_config_empty_rules_uses_defaults():
    """PermissionsConfig 中 rules 为空时应使用默认规则。"""
    perms = PermissionsConfig(rules=[])
    engine = load_permission_engine(perms)
    assert len(engine.rules) == 10

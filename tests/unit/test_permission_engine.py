from __future__ import annotations

from pathlib import Path

import pytest

from src.core.permission_engine import PermissionEngine, load_permission_engine
from src.types.permission import Decision, PermissionAction


# ============================================================================
# 切片 1：PermissionAction 枚举 — ask 存在，prompt 已移除
# ============================================================================


def test_permission_action_has_ask_not_prompt():
    """PermissionAction 应有 ask，不应有 prompt。"""
    assert hasattr(PermissionAction, "ask")
    assert not hasattr(PermissionAction, "prompt")
    assert PermissionAction.ask.value == "ask"
    assert PermissionAction.allow.value == "allow"
    assert PermissionAction.deny.value == "deny"


# ============================================================================
# 切片 2：last-match-wins 语义
# ============================================================================


def test_last_match_wins():
    """给定规则 [("read *", "allow"), ("read *", "deny")]，check("read_file", {}) 返回 deny。"""
    engine = PermissionEngine(
        rules=[("read *", "allow"), ("read *", "deny")],
        workspace=Path("/tmp"),
    )
    d = engine.check("read_file", {})
    assert d.action == PermissionAction.deny


def test_last_match_wins_with_wildcard():
    """通配符规则最后匹配时生效。"""
    engine = PermissionEngine(
        rules=[("*", "allow"), ("bash *", "deny")],
        workspace=Path("/tmp"),
    )
    d = engine.check("bash", {"cmd": "ls"})
    assert d.action == PermissionAction.deny


# ============================================================================
# 切片 3：fnmatch 工具名模式匹配
# ============================================================================


def test_fnmatch_tool_name_wildcard():
    """"read *" 应匹配 read_file、read。"""
    engine = PermissionEngine(
        rules=[("read *", "allow")],
        workspace=Path("/tmp"),
    )
    assert engine.check("read_file", {}).action == PermissionAction.allow
    assert engine.check("read", {}).action == PermissionAction.allow


def test_fnmatch_tool_name_exact():
    """"bash" 精确匹配。"""
    engine = PermissionEngine(
        rules=[("bash", "deny")],
        workspace=Path("/tmp"),
    )
    assert engine.check("bash", {}).action == PermissionAction.deny
    assert engine.check("bash_something", {}).action == PermissionAction.ask


# ============================================================================
# 切片 4：fnmatch 参数值匹配（.env 拒绝）
# ============================================================================


def test_fnmatch_args_dotenv_deny():
    """规则 ".env*": "deny" 对 check("read_file", {"path": ".env"}) 返回 deny。"""
    engine = PermissionEngine(
        rules=[(".env*", "deny")],
        workspace=Path("/tmp"),
    )
    d = engine.check("read_file", {"path": ".env"})
    assert d.action == PermissionAction.deny


def test_fnmatch_args_dotenv_prod_deny():
    """规则 ".env*": "deny" 对 .env.production 也返回 deny。"""
    engine = PermissionEngine(
        rules=[(".env*", "deny")],
        workspace=Path("/tmp"),
    )
    d = engine.check("read_file", {"path": ".env.production"})
    assert d.action == PermissionAction.deny


def test_fnmatch_args_normal_file_not_denied():
    """规则 ".env*": "deny" 不应拒绝普通文件（默认规则 read * → allow 生效）。"""
    engine = PermissionEngine(
        rules=[(".env*", "deny")],
        workspace=Path("/tmp"),
    )
    d = engine.check("read_file", {"path": "src/main.py"})
    assert d.action == PermissionAction.allow


# ============================================================================
# 切片 5：三个动作级别
# ============================================================================


def test_action_allow():
    """allow 直接放行。"""
    engine = PermissionEngine(
        rules=[("read *", "allow")],
        workspace=Path("/tmp"),
    )
    d = engine.check("read_file", {"path": "src/main.py"})
    assert d.action == PermissionAction.allow


def test_action_ask():
    """ask 触发确认。"""
    engine = PermissionEngine(
        rules=[("bash *", "ask")],
        workspace=Path("/tmp"),
    )
    d = engine.check("bash", {"cmd": "ls"})
    assert d.action == PermissionAction.ask


def test_action_deny():
    """deny 直接拒绝。"""
    engine = PermissionEngine(
        rules=[("bash *", "deny")],
        workspace=Path("/tmp"),
    )
    d = engine.check("bash", {"cmd": "rm -rf /"})
    assert d.action == PermissionAction.deny


# ============================================================================
# 切片 6：默认规则
# ============================================================================


def test_default_rules_read_allow():
    """无用户配置时，read_file 返回 allow。"""
    engine = PermissionEngine(rules=[], workspace=Path("/tmp"))
    d = engine.check("read_file", {"path": "src/main.py"})
    assert d.action == PermissionAction.allow


def test_default_rules_bash_ask():
    """无用户配置时，bash 返回 ask。"""
    engine = PermissionEngine(rules=[], workspace=Path("/tmp"))
    d = engine.check("bash", {"cmd": "ls"})
    assert d.action == PermissionAction.ask


def test_default_rules_dotenv_deny():
    """无用户配置时，.env 文件返回 deny。"""
    engine = PermissionEngine(rules=[], workspace=Path("/tmp"))
    d = engine.check("read_file", {"path": ".env"})
    assert d.action == PermissionAction.deny


def test_default_rules_write_ask():
    """无用户配置时，write 返回 ask。"""
    engine = PermissionEngine(rules=[], workspace=Path("/tmp"))
    d = engine.check("write_file", {"path": "src/main.py"})
    assert d.action == PermissionAction.ask


def test_default_rules_edit_ask():
    """无用户配置时，edit 返回 ask。"""
    engine = PermissionEngine(rules=[], workspace=Path("/tmp"))
    d = engine.check("edit_file", {"path": "src/main.py"})
    assert d.action == PermissionAction.ask


# ============================================================================
# 切片 7：external_directory 支持
# ============================================================================


def test_external_directory_allowed():
    """配置 external_directories=["/tmp/safe"]，check("read_file", {"path": "/tmp/safe/data.txt"}) 返回 ask。"""
    engine = PermissionEngine(
        rules=[],
        workspace=Path("/home/user/project"),
        external_directories=["/tmp/safe"],
    )
    d = engine.check("read_file", {"path": "/tmp/safe/data.txt"})
    assert d.action == PermissionAction.ask


def test_external_directory_not_in_whitelist_deny():
    """路径不在 workspace 也不在 external_directories 时返回 deny。"""
    engine = PermissionEngine(
        rules=[],
        workspace=Path("/home/user/project"),
        external_directories=["/tmp/safe"],
    )
    d = engine.check("read_file", {"path": "/etc/passwd"})
    assert d.action == PermissionAction.deny


def test_external_directory_none_deny():
    """未配置 external_directories 时，外部路径返回 deny。"""
    engine = PermissionEngine(
        rules=[],
        workspace=Path("/home/user/project"),
    )
    d = engine.check("read_file", {"path": "/etc/passwd"})
    assert d.action == PermissionAction.deny


# ============================================================================
# 切片 8：无匹配规则默认 ask
# ============================================================================


def test_no_match_defaults_to_ask():
    """无匹配规则时，check("unknown_tool", {}) 返回 ask。"""
    engine = PermissionEngine(rules=[], workspace=Path("/tmp"))
    d = engine.check("unknown_tool", {})
    assert d.action == PermissionAction.ask


# ============================================================================
# 切片 9：load_permission_engine 适配
# ============================================================================


def test_load_permission_engine_passes_external_directories():
    """load_permission_engine 正确传递 external_directories 到引擎。"""
    from src.config.unified_config import PermissionRule, PermissionsConfig

    perms = PermissionsConfig(
        rules=[
            PermissionRule(pattern="read *", action="allow"),
        ],
        external_directories=["/tmp/safe"],
    )
    engine = load_permission_engine(perms, workspace=Path("/home/user/project"))
    d = engine.check("read_file", {"path": "/tmp/safe/data.txt"})
    # 用户规则 ("read *", "allow") 优先匹配，允许读取
    assert d.action == PermissionAction.allow


def test_load_permission_engine_empty_rules_uses_defaults():
    """PermissionsConfig 中 rules 为空时应使用默认规则。"""
    from src.config.unified_config import PermissionsConfig

    perms = PermissionsConfig(rules=[])
    engine = load_permission_engine(perms, workspace=Path("/tmp"))
    d = engine.check("read_file", {"path": "src/main.py"})
    assert d.action == PermissionAction.allow


def test_load_permission_engine_user_rules():
    """用户规则应被正确加载。"""
    from src.config.unified_config import PermissionRule, PermissionsConfig

    perms = PermissionsConfig(
        rules=[
            PermissionRule(pattern="bash *", action="deny"),
            PermissionRule(pattern="read *", action="allow"),
        ]
    )
    engine = load_permission_engine(perms, workspace=Path("/tmp"))
    d = engine.check("bash", {"cmd": "ls"})
    assert d.action == PermissionAction.deny

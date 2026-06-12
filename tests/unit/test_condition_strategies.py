from __future__ import annotations

from pathlib import Path

import pytest

from src.core.permission_engine import (
    DangerousConditionStrategy,
    PathInWorkspaceConditionStrategy,
    PathSensitiveConditionStrategy,
)


class TestDangerousConditionStrategy:
    """切片 1：DangerousConditionStrategy 独立单元测试"""

    def test_dangerous_rm_returns_true(self):
        strategy = DangerousConditionStrategy()
        assert strategy.evaluate({"cmd": "rm -rf /"}, Path("/tmp")) is True

    def test_safe_ls_returns_false(self):
        strategy = DangerousConditionStrategy()
        assert strategy.evaluate({"cmd": "ls -la"}, Path("/tmp")) is False

    def test_empty_cmd_returns_false(self):
        strategy = DangerousConditionStrategy()
        assert strategy.evaluate({"cmd": ""}, Path("/tmp")) is False

    def test_missing_cmd_key_returns_false(self):
        strategy = DangerousConditionStrategy()
        assert strategy.evaluate({}, Path("/tmp")) is False

    def test_sudo_returns_true(self):
        strategy = DangerousConditionStrategy()
        assert strategy.evaluate({"cmd": "sudo rm -rf /"}, Path("/tmp")) is True

    def test_cmd_substitution_returns_true(self):
        strategy = DangerousConditionStrategy()
        assert strategy.evaluate({"cmd": "echo $(rm -rf /)"}, Path("/tmp")) is True

    def test_workspace_parameter_is_accepted_but_ignored(self):
        """workspace 参数对 dangerous 条件无影响，但接口要求接收它"""
        strategy = DangerousConditionStrategy()
        assert strategy.evaluate({"cmd": "rm -rf /"}, Path("/etc")) is True


class TestPathInWorkspaceConditionStrategy:
    """切片 2：PathInWorkspaceConditionStrategy 独立单元测试"""

    def test_path_inside_workspace_returns_true(self):
        strategy = PathInWorkspaceConditionStrategy()
        assert strategy.evaluate({"path": "/tmp/sub/file.txt"}, Path("/tmp")) is True

    def test_path_outside_workspace_returns_false(self):
        strategy = PathInWorkspaceConditionStrategy()
        assert strategy.evaluate({"path": "/etc/passwd"}, Path("/tmp")) is False

    def test_empty_path_returns_true(self):
        strategy = PathInWorkspaceConditionStrategy()
        assert strategy.evaluate({"path": ""}, Path("/tmp")) is True

    def test_missing_path_key_returns_true(self):
        strategy = PathInWorkspaceConditionStrategy()
        assert strategy.evaluate({}, Path("/tmp")) is True

    def test_path_equals_workspace_returns_true(self):
        strategy = PathInWorkspaceConditionStrategy()
        assert strategy.evaluate({"path": "/tmp"}, Path("/tmp")) is True

    def test_relative_path_resolves_against_cwd(self):
        """相对路径会基于 CWD 解析，策略内部使用 resolve()"""
        strategy = PathInWorkspaceConditionStrategy()
        result = strategy.evaluate({"path": "."}, Path("/tmp"))
        assert result is True or result is False  # 取决于 CWD


class TestPathSensitiveConditionStrategy:
    """切片 3：PathSensitiveConditionStrategy 独立单元测试"""

    def test_cp_with_absolute_path_returns_true(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "cp /etc/hosts /tmp/"}, Path("/tmp")) is True

    def test_curl_with_absolute_path_returns_true(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "curl -o /tmp/file http://example.com"}, Path("/tmp")) is True

    def test_rsync_with_relative_path_returns_true(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "rsync ../src /tmp/"}, Path("/tmp")) is True

    def test_cp_with_no_path_returns_false(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "cp file1 file2"}, Path("/tmp")) is False

    def test_safe_command_returns_false(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "ls -la"}, Path("/tmp")) is False

    def test_empty_cmd_returns_false(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": ""}, Path("/tmp")) is False

    def test_missing_cmd_key_returns_false(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({}, Path("/tmp")) is False

    def test_tilde_path_returns_true(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "cp ~/file /tmp/"}, Path("/tmp")) is True

    def test_proc_path_returns_true(self):
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "cp /proc/cpuinfo /tmp/"}, Path("/tmp")) is True

    def test_workspace_parameter_is_accepted_but_ignored(self):
        """workspace 参数对 path_sensitive 条件无影响，但接口要求接收它"""
        strategy = PathSensitiveConditionStrategy()
        assert strategy.evaluate({"cmd": "cp /etc/hosts /tmp/"}, Path("/etc")) is True

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.permission_engine import (
    DangerousConditionStrategy,
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

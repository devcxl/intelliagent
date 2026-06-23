from __future__ import annotations

from pathlib import Path

import pytest

from src.core.permission_engine import PermissionEngine
from src.core.react_engine import ReactEngine
from src.runtime.permission_callback import CliCallback


class MockLLMClient:
    pass


class MockRegistry:
    def get_tool_fn(self, name: str):
        async def _echo(**kwargs):
            return f'{{"status": "success", "output": {kwargs}}}'

        return _echo

    def get_openai_tools(self):
        return []


def _make_engine(rules: list[tuple[str, str]], callback=None, workspace=None):
    pe = PermissionEngine(rules=rules, workspace=workspace or Path.cwd())
    return ReactEngine(
        llm_client=MockLLMClient(),
        tools_registry=MockRegistry(),
        permission_engine=pe,
        permission_callback=callback,
    )


@pytest.mark.asyncio
async def test_allow_executes_directly():
    engine = _make_engine(
        [("run_shell", "allow")],
    )
    result = await engine.execute_tool({"function": {"name": "run_shell", "arguments": '{"cmd": "ls"}'}})
    assert "success" in result


@pytest.mark.asyncio
async def test_deny_blocks():
    engine = _make_engine(
        [("run_shell", "deny")],
    )
    result = await engine.execute_tool({"function": {"name": "run_shell", "arguments": '{"cmd": "rm -rf /"}'}})
    assert "权限拒绝" in result
    assert "error" in result


@pytest.mark.asyncio
async def test_ask_approved_executes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    cb = CliCallback(timeout=10.0)
    engine = _make_engine(
        [("run_shell", "ask")],
        callback=cb,
    )
    result = await engine.execute_tool({"function": {"name": "run_shell", "arguments": '{"cmd": "rm -rf /"}'}})
    assert "success" in result


@pytest.mark.asyncio
async def test_ask_rejected_blocks(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    cb = CliCallback(timeout=10.0)
    engine = _make_engine(
        [("run_shell", "ask")],
        callback=cb,
    )
    result = await engine.execute_tool({"function": {"name": "run_shell", "arguments": '{"cmd": "ls"}'}})
    assert "用户拒绝执行" in result


@pytest.mark.asyncio
async def test_no_permission_engine_executes_directly():
    engine = ReactEngine(
        llm_client=MockLLMClient(),
        tools_registry=MockRegistry(),
    )
    result = await engine.execute_tool({"function": {"name": "run_shell", "arguments": '{"cmd": "ls"}'}})
    assert "success" in result


@pytest.mark.asyncio
async def test_path_in_workspace_allows(tmp_path):
    test_file = tmp_path / "test.py"
    test_file.write_text("x=1")
    engine = _make_engine(
        [("read *", "allow")],
        workspace=tmp_path,
    )
    result = await engine.execute_tool({"function": {"name": "read_file", "arguments": f'{{"path": "{test_file}"}}'}})
    assert "success" in result


@pytest.mark.asyncio
async def test_path_outside_workspace_denies(tmp_path):
    engine = _make_engine(
        [],
        workspace=tmp_path,
    )
    result = await engine.execute_tool({"function": {"name": "read_file", "arguments": '{"path": "/etc/passwd"}'}})
    assert "权限拒绝" in result

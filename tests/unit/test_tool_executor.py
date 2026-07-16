from __future__ import annotations

import json
from typing import Any

import pytest

from src.core.tool_executor import ToolExecutor
from src.permission import Decision, PermissionAction


class MockRegistry:
    def get_openai_tools(self):
        return []

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str:
        return json.dumps({"status": "success", "output": {**kwargs}})


class DenyEngine:
    def check(self, tool_name: str, args: dict) -> Decision:
        return Decision(action=PermissionAction.deny, reason="denied")


class AllowEngine:
    def check(self, tool_name: str, args: dict) -> Decision:
        return Decision(action=PermissionAction.allow, reason="allowed")


class AskEngine:
    def check(self, tool_name: str, args: dict) -> Decision:
        return Decision(action=PermissionAction.ask, reason="needs confirmation")


class ApproveCallback:
    async def on_prompt(self, tool_name: str, args: dict, reason: str) -> bool:
        return True


class RejectCallback:
    async def on_prompt(self, tool_name: str, args: dict, reason: str) -> bool:
        return False


@pytest.mark.asyncio
async def test_allow_executes():
    executor = ToolExecutor(registry=MockRegistry(), permission_engine=AllowEngine())
    result = await executor.execute({"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "test.py"}'}})
    assert result.status == "success"
    assert "success" in result.content


@pytest.mark.asyncio
async def test_deny_blocks():
    executor = ToolExecutor(registry=MockRegistry(), permission_engine=DenyEngine())
    result = await executor.execute(
        {"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "/etc/passwd"}'}}
    )
    assert result.status == "denied"
    assert "权限拒绝" in result.content


@pytest.mark.asyncio
async def test_ask_approved_executes():
    executor = ToolExecutor(
        registry=MockRegistry(), permission_engine=AskEngine(), permission_callback=ApproveCallback()
    )
    result = await executor.execute({"id": "c1", "function": {"name": "read_file", "arguments": "{}"}})
    assert result.status == "success"


@pytest.mark.asyncio
async def test_ask_rejected_blocks():
    executor = ToolExecutor(
        registry=MockRegistry(), permission_engine=AskEngine(), permission_callback=RejectCallback()
    )
    result = await executor.execute({"id": "c1", "function": {"name": "read_file", "arguments": "{}"}})
    assert result.status == "rejected"
    assert "用户拒绝" in result.content


@pytest.mark.asyncio
async def test_ask_without_callback():
    executor = ToolExecutor(registry=MockRegistry(), permission_engine=AskEngine())
    result = await executor.execute({"id": "c1", "function": {"name": "read_file", "arguments": "{}"}})
    assert result.status == "no_callback"


@pytest.mark.asyncio
async def test_invalid_json_args():
    executor = ToolExecutor(registry=MockRegistry())
    result = await executor.execute({"id": "c1", "function": {"name": "read_file", "arguments": "not json"}})
    assert result.status == "success"


@pytest.mark.asyncio
async def test_no_permission_engine():
    executor = ToolExecutor(registry=MockRegistry())
    result = await executor.execute({"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}})
    assert result.status == "success"


@pytest.mark.asyncio
async def test_result_fields():
    executor = ToolExecutor(registry=MockRegistry())
    result = await executor.execute({"id": "call_abc", "function": {"name": "echo", "arguments": '{"msg": "hello"}'}})
    assert result.tool_call_id == "call_abc"
    assert result.tool_name == "echo"
    assert result.tool_args == {"msg": "hello"}


class FailingRegistry:
    def get_openai_tools(self):
        return []

    async def call_tool(self, tool_name: str, **kwargs: Any) -> str:
        raise RuntimeError("工具内部错误")


@pytest.mark.asyncio
async def test_tool_exception_caught():
    """工具抛异常时返回 error 结果，不传播异常。"""
    executor = ToolExecutor(registry=FailingRegistry())
    result = await executor.execute({"id": "c1", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}})
    assert result.status == "error"
    assert "工具内部错误" in result.error
    assert "工具执行异常" in result.content


@pytest.mark.asyncio
async def test_tool_exception_does_not_propagate():
    """工具异常不传播到调用方。"""
    executor = ToolExecutor(registry=FailingRegistry())
    result = await executor.execute({"id": "c1", "function": {"name": "bomb", "arguments": "{}"}})
    assert result.status == "error"
    assert result.tool_name == "bomb"

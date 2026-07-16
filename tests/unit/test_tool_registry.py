"""ToolRegistry / response / time_tool 单元测试。

覆盖工具注册表的注册/调用/注销、响应构建工具、时间工具。
与 test_builtin_tools.py 互补，后者已覆盖 shell/file/edit 工具。
"""

from __future__ import annotations

import json
from datetime import datetime

from src.tools.registry import NoopToolRegistry, ToolRegistry
from src.tools.response import error_response, success_response
from src.tools.time_tool import CST, get_current_time

# ============================================================================
# response.py
# ============================================================================


class TestSuccessResponse:
    def test_with_data(self):
        result = json.loads(success_response({"output": "hello"}))
        assert result["status"] == "ok"
        assert result["output"] == "hello"

    def test_empty_data(self):
        result = json.loads(success_response({}))
        assert result["status"] == "ok"
        assert len(result) == 1

    def test_unicode_preserved(self):
        result = json.loads(success_response({"msg": "中文测试"}))
        assert result["msg"] == "中文测试"

    def test_multiple_keys(self):
        result = json.loads(success_response({"a": 1, "b": [2, 3]}))
        assert result["a"] == 1
        assert result["b"] == [2, 3]


class TestErrorResponse:
    def test_with_code(self):
        result = json.loads(error_response("出错了", "MY_ERROR"))
        assert result["status"] == "error"
        assert result["error"] == "出错了"
        assert result["code"] == "MY_ERROR"

    def test_default_code(self):
        result = json.loads(error_response("出错了"))
        assert result["code"] == "UNKNOWN_ERROR"

    def test_unicode_error_message(self):
        result = json.loads(error_response("文件不存在", "FILE_NOT_FOUND"))
        assert result["error"] == "文件不存在"


# ============================================================================
# time_tool.py
# ============================================================================


class TestGetCurrentTime:
    async def test_returns_cst_time(self):
        result = await get_current_time()
        parts = result.split()
        assert len(parts) == 3
        datetime.strptime(parts[0] + " " + parts[1], "%Y-%m-%d %H:%M:%S")
        assert parts[2] == "Asia/Shanghai"

    async def test_cst_timezone_offset(self):
        from datetime import timedelta, timezone

        assert CST == timezone(timedelta(hours=8))


# ============================================================================
# ToolRegistry
# ============================================================================


class TestToolRegistry:
    async def test_register_and_call(self):
        registry = ToolRegistry()

        async def echo(msg: str) -> str:
            return success_response({"echo": msg})

        registry.register(
            fn=echo, name="echo", description="回声", parameters={"msg": {"type": "string", "required": True}}
        )

        result = await registry.call_tool("echo", msg="hello")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["echo"] == "hello"

    async def test_call_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.call_tool("nonexistent")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "UNKNOWN_TOOL"

    async def test_unregister(self):
        registry = ToolRegistry()

        async def noop() -> str:
            return success_response({})

        registry.register(fn=noop, name="noop", description="空操作", parameters={})
        assert "noop" in registry.list_tool_names()

        registry.unregister("noop")
        assert "noop" not in registry.list_tool_names()

    async def test_unregister_nonexistent_silent(self):
        registry = ToolRegistry()
        registry.unregister("nonexistent")

    async def test_get_openai_tools(self):
        registry = ToolRegistry()

        async def dummy() -> str:
            return ""

        registry.register(
            fn=dummy, name="dummy", description="测试工具", parameters={"x": {"type": "string", "required": True}}
        )

        tools = registry.get_openai_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "dummy"
        assert tools[0]["function"]["description"] == "测试工具"
        assert tools[0]["function"]["parameters"]["required"] == ["x"]

    async def test_get_openai_tools_empty(self):
        registry = ToolRegistry()
        assert registry.get_openai_tools() == []

    async def test_call_tool_with_type_error(self):
        registry = ToolRegistry()

        async def need_arg(path: str) -> str:
            return success_response({"path": path})

        registry.register(
            fn=need_arg,
            name="need_arg",
            description="需要参数",
            parameters={"path": {"type": "string", "required": True}},
        )

        result = await registry.call_tool("need_arg")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "INVALID_PARAMETERS"

    async def test_call_tool_with_runtime_error(self):
        registry = ToolRegistry()

        async def boom() -> str:
            raise RuntimeError("内部错误")

        registry.register(fn=boom, name="boom", description="爆炸", parameters={})

        result = await registry.call_tool("boom")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "EXECUTION_ERROR"
        assert "内部错误" in data["error"]

    async def test_decorator_register(self):
        registry = ToolRegistry()

        @registry.tool(name="decorated", description="装饰器注册", parameters={})
        async def decorated() -> str:
            return success_response({"ok": True})

        assert "decorated" in registry.list_tool_names()
        result = await registry.call_tool("decorated")
        data = json.loads(result)
        assert data["ok"] is True

    def test_get_tool_fn_found(self):
        registry = ToolRegistry()

        async def my_fn() -> str:
            return ""

        registry.register(fn=my_fn, name="my_fn", description="", parameters={})
        fn = registry.get_tool_fn("my_fn")
        assert fn is my_fn

    def test_get_tool_fn_not_found(self):
        registry = ToolRegistry()
        assert registry.get_tool_fn("nonexistent") is None

    def test_list_tool_names(self):
        registry = ToolRegistry()

        async def a() -> str:
            return ""

        async def b() -> str:
            return ""

        registry.register(fn=a, name="a", description="", parameters={})
        registry.register(fn=b, name="b", description="", parameters={})
        names = registry.list_tool_names()
        assert set(names) == {"a", "b"}


# ============================================================================
# NoopToolRegistry
# ============================================================================


class TestNoopToolRegistry:
    async def test_get_openai_tools_empty(self):
        registry = NoopToolRegistry()
        assert registry.get_openai_tools() == []

    async def test_call_tool_returns_error(self):
        registry = NoopToolRegistry()
        result = await registry.call_tool("anything")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "UNKNOWN_TOOL"

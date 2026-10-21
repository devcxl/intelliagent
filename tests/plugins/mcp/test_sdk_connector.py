"""MCP SDK 连接器测试：传输选择（stdio / streamable HTTP / SSE）、类型适配与 anyio 跨 task 生命周期修复。

旧缺陷（docs/2026-10-21-project-analysis-and-roadmap.md + 旧 MCPClientManager）：
按 "405" 错误字符串嗅探回退 SSE；anyio CancelScope 上下文跨 task 退出会崩溃，生命周期脆弱。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from mcp.types import CallToolResult, ImageContent, ListToolsResult, TextContent, Tool

import src.plugins.mcp.sdk_connector as sdk_connector
from src.plugins.mcp.config import McpServerConfig
from src.plugins.mcp.connection import McpCallResult, McpToolDefinition
from src.plugins.mcp.sdk_connector import McpSdkConnector, SdkSession
from tests.plugins.mcp.fakes import demo_server, tool_definition


def fake_streams(*streams: Any) -> Any:
    """产出 (read, write[, get_session_id]) 的假传输上下文。"""

    @asynccontextmanager
    async def opened() -> Any:
        yield streams

    return opened()


class RecordingTransport:
    """记录 SDK 传输工厂收到的参数，并返回假传输上下文。"""

    def __init__(self, *streams: Any) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._streams = streams

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return fake_streams(*self._streams)


class TestTransportSelection:
    async def test_stdio_transport_spawns_the_configured_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorder = RecordingTransport("read", "write")
        monkeypatch.setattr(sdk_connector, "stdio_client", recorder)
        server = McpServerConfig(
            name="local",
            transport="stdio",
            command=["uvx", "srv", "--flag"],
            env={"K": "V"},
            cwd="/tmp",
        )

        async with sdk_connector.open_streams(server) as streams:
            pass

        (params,) = recorder.calls[0][0]
        assert recorder.calls[0][1] == {}
        assert params.command == "uvx"
        assert params.args == ["srv", "--flag"]
        assert params.env == {"K": "V"}
        assert params.cwd == "/tmp"
        assert streams == ("read", "write")

    async def test_streamable_http_transport_uses_url_and_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorder = RecordingTransport("read", "write", lambda: "session-id")
        monkeypatch.setattr(sdk_connector, "streamable_http_client", recorder)
        server = McpServerConfig(
            name="remote",
            transport="streamable_http",
            url="https://example.com/mcp",
            headers={"Authorization": "Bearer x"},
        )

        async with sdk_connector.open_streams(server) as streams:
            http_client = recorder.calls[0][1]["http_client"]
            assert isinstance(http_client, httpx.AsyncClient)
            assert http_client.headers.get("Authorization") == "Bearer x"
            assert http_client.is_closed is False

        assert recorder.calls[0][1]["url"] == "https://example.com/mcp"
        assert streams == ("read", "write")
        assert http_client.is_closed is True

    async def test_sse_transport_uses_url_and_timeouts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorder = RecordingTransport("read", "write")
        monkeypatch.setattr(sdk_connector, "sse_client", recorder)
        server = McpServerConfig(
            name="legacy",
            transport="sse",
            url="https://example.com/sse",
            headers={"X-Api": "k"},
            timeout=7.0,
            sse_read_timeout=60.0,
        )

        async with sdk_connector.open_streams(server) as streams:
            pass

        kwargs = recorder.calls[0][1]
        assert kwargs["url"] == "https://example.com/sse"
        assert kwargs["headers"] == {"X-Api": "k"}
        assert kwargs["timeout"] == 7.0
        assert kwargs["sse_read_timeout"] == 60.0
        assert streams == ("read", "write")


class FakeRawSession:
    """SDK ClientSession 的最小替身：分页 list_tools 与 call_tool。"""

    def __init__(
        self,
        pages: dict[str | None, ListToolsResult] | None = None,
        call_result: CallToolResult | None = None,
    ) -> None:
        self._pages = pages or {None: ListToolsResult(tools=[])}
        self._call_result = call_result or CallToolResult(content=[], isError=False)
        self.listed_cursors: list[str | None] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self, cursor: str | None = None, **_kwargs: Any) -> ListToolsResult:
        self.listed_cursors.append(cursor)
        return self._pages[cursor]

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None, **_kwargs: Any) -> CallToolResult:
        self.calls.append((name, dict(arguments or {})))
        return self._call_result


class TestSdkSessionAdapter:
    async def test_list_tools_maps_definitions_with_full_input_schema(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "object", "properties": {"y": {"enum": [1, 2]}}}}}
        raw = FakeRawSession({None: ListToolsResult(tools=[Tool(name="t", description="d", inputSchema=schema)])})
        session = SdkSession(raw)

        definitions = await session.list_tools()

        assert definitions == [McpToolDefinition(name="t", description="d", input_schema=schema)]

    async def test_list_tools_follows_pagination(self) -> None:
        raw = FakeRawSession(
            {
                None: ListToolsResult(tools=[Tool(name="a", inputSchema={})], nextCursor="c2"),
                "c2": ListToolsResult(tools=[Tool(name="b", inputSchema={})]),
            }
        )
        session = SdkSession(raw)

        definitions = await session.list_tools()

        assert [item.name for item in definitions] == ["a", "b"]
        assert raw.listed_cursors == [None, "c2"]

    async def test_call_tool_joins_text_blocks(self) -> None:
        raw = FakeRawSession(
            call_result=CallToolResult(
                content=[TextContent(type="text", text="hello"), TextContent(type="text", text="world")],
                isError=False,
            )
        )
        session = SdkSession(raw)

        result = await session.call_tool("t", {"x": 1})

        assert result == McpCallResult(text="hello\nworld", is_error=False)
        assert raw.calls == [("t", {"x": 1})]

    async def test_call_tool_serializes_non_text_blocks(self) -> None:
        raw = FakeRawSession(
            call_result=CallToolResult(
                content=[ImageContent(type="image", data="aGk=", mimeType="image/png")],
                isError=True,
            )
        )
        session = SdkSession(raw)

        result = await session.call_tool("t", {})

        assert result.is_error is True
        assert "image/png" in result.text


class RecordingSession:
    """记录生命周期所在 task 的假 McpSession。"""

    def __init__(self) -> None:
        self.enter_task: asyncio.Task[Any] | None = None
        self.exit_task: asyncio.Task[Any] | None = None
        self.tools = [tool_definition("echo")]

    async def list_tools(self) -> list[McpToolDefinition]:
        return list(self.tools)

    async def call_tool(self, name: str, arguments: Any) -> McpCallResult:
        return McpCallResult(text="ok", is_error=False)


def strict_session_factory(sessions: list[RecordingSession], *, fail: Exception | None = None) -> Any:
    """构造会话上下文工厂：进入/退出记录所在 task，跨 task 退出即报错（模拟 anyio 语义）。"""

    @asynccontextmanager
    async def factory(_server: McpServerConfig) -> Any:
        if fail is not None:
            raise fail
        session = RecordingSession()
        session.enter_task = asyncio.current_task()
        sessions.append(session)
        yield session
        session.exit_task = asyncio.current_task()
        if session.exit_task is not session.enter_task:
            raise RuntimeError("cancel scope exited in a different task")

    return factory


class TestConnectionLifecycle:
    async def test_context_is_entered_and_exited_in_one_task(self) -> None:
        """connect 与 close 可在不同 task 调用；SDK 上下文仍同 task 进入/退出（anyio 要求）。"""
        sessions: list[RecordingSession] = []
        connector = McpSdkConnector(session_factory=strict_session_factory(sessions))
        connection = await connector.connect(demo_server())

        async def close_from_another_task() -> None:
            await connection.close()

        await asyncio.create_task(close_from_another_task())

        assert sessions[0].enter_task is not None
        assert sessions[0].exit_task is sessions[0].enter_task

    async def test_connector_delegates_tool_discovery_and_calls(self) -> None:
        sessions: list[RecordingSession] = []
        connector = McpSdkConnector(session_factory=strict_session_factory(sessions))
        connection = await connector.connect(demo_server())

        definitions = await connection.list_tools()
        result = await connection.call_tool("echo", {"x": 1})
        await connection.close()

        assert [item.name for item in definitions] == ["echo"]
        assert result == McpCallResult(text="ok", is_error=False)

    async def test_close_is_idempotent(self) -> None:
        sessions: list[RecordingSession] = []
        connector = McpSdkConnector(session_factory=strict_session_factory(sessions))
        connection = await connector.connect(demo_server())

        await connection.close()
        await connection.close()

        assert sessions[0].exit_task is sessions[0].enter_task

    async def test_connect_failure_propagates_the_underlying_reason(self) -> None:
        connector = McpSdkConnector(session_factory=strict_session_factory([], fail=RuntimeError("handshake failed")))

        with pytest.raises(RuntimeError, match="handshake failed"):
            await connector.connect(demo_server())

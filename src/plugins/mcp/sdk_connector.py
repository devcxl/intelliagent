"""MCP SDK 连接器：stdio / streamable HTTP / SSE 传输 + 单 task 生命周期（修 anyio 跨 task 退出缺陷）。

mcp SDK 的传输与会话上下文建立在 anyio CancelScope 上，要求 __aenter__/__aexit__ 在同一 task 完成；
旧 MCPClientManager 让进入/退出随调用方 task 漂移，跨 task 关闭即崩溃。_ConnectionRunner 把连接上下文
固定在专用 task 内进入/退出，connect()/close() 因此可从任意 task 调用。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import ContentBlock

from src.plugins.mcp.config import McpServerConfig
from src.plugins.mcp.connection import McpCallResult, McpConnection, McpSession, McpToolDefinition

SessionFactory = Callable[[McpServerConfig], AbstractAsyncContextManager[McpSession]]
"""会话上下文工厂：进入即得到 McpSession，退出即关闭传输与会话（默认 open_sdk_session）。"""

_CLOSE_WAIT_SECONDS = 5.0
"""close 时等待 runner task 自行退出的上限；超时才强制取消（不让 close 无限挂）。"""


def open_streams(server: McpServerConfig) -> AbstractAsyncContextManager[tuple[Any, Any]]:
    """按 transport 显式选择传输（stdio / streamable HTTP / SSE），产出 (read, write) 流。

    不再按错误字符串嗅探回退（旧 405 缺陷）：接入方式由配置声明，配置与实际传输一一对应。
    """
    if server.transport == "stdio":
        return stdio_client(
            StdioServerParameters(
                command=server.command[0],
                args=server.command[1:],
                env=server.env,
                cwd=server.cwd,
            )
        )
    if server.transport == "streamable_http":
        return _open_streamable_http(server)
    return sse_client(
        url=server.url,
        headers=server.headers,
        timeout=server.timeout,
        sse_read_timeout=server.sse_read_timeout,
    )


@asynccontextmanager
async def _open_streamable_http(server: McpServerConfig) -> AsyncIterator[tuple[Any, Any]]:
    """streamable HTTP 传输：headers/timeout 经 httpx 客户端注入，随传输一起关闭。"""
    async with httpx.AsyncClient(headers=server.headers, timeout=server.timeout) as http_client:
        async with streamable_http_client(url=server.url, http_client=http_client) as streams:
            read_stream, write_stream, _get_session_id = streams
            yield read_stream, write_stream


def format_content(blocks: Sequence[ContentBlock]) -> str:
    """把 MCP 内容块拼成文本：text 块原样，非文本块转紧凑 JSON（信息不丢）。"""
    return "\n".join(_format_block(block) for block in blocks)


def _format_block(block: ContentBlock) -> str:
    text = getattr(block, "text", None)
    if isinstance(text, str) and text:
        return text
    return block.model_dump_json(by_alias=True, exclude_none=True)


class SdkSession:
    """mcp SDK ClientSession → McpSession 适配：inputSchema 原样映射，内容块转统一文本。"""

    def __init__(self, session: ClientSession) -> None:
        self._session = session

    async def list_tools(self) -> list[McpToolDefinition]:
        """发现工具（跟随分页游标）；inputSchema 原样透传，不扁平化、不丢嵌套结构。"""
        definitions: list[McpToolDefinition] = []
        cursor: str | None = None
        while True:
            page = await self._session.list_tools(cursor=cursor)
            for tool in page.tools:
                definitions.append(
                    McpToolDefinition(
                        name=tool.name,
                        description=tool.description or "",
                        input_schema=dict(tool.inputSchema),
                    )
                )
            cursor = page.nextCursor
            if not cursor:
                return definitions

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> McpCallResult:
        result = await self._session.call_tool(name, dict(arguments))
        return McpCallResult(text=format_content(result.content), is_error=bool(result.isError))


@asynccontextmanager
async def open_sdk_session(server: McpServerConfig) -> AsyncIterator[McpSession]:
    """打开传输与会话并完成 initialize，产出 McpSession；退出即整体关闭。"""
    async with AsyncExitStack() as stack:
        read_stream, write_stream = await stack.enter_async_context(open_streams(server))
        session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        yield SdkSession(session)


class McpSdkConnector:
    """基于 mcp SDK 的 McpConnector：传输选择显式，连接上下文由 runner task 唯一持有。"""

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory if session_factory is not None else open_sdk_session

    async def connect(self, server: McpServerConfig) -> McpConnection:
        return await _ConnectionRunner(self._session_factory(server)).start()


class _ConnectionRunner:
    """单个服务器的连接生命周期：上下文进入/退出都在 runner task 内完成（McpConnection 实现）。"""

    def __init__(self, session_cm: AbstractAsyncContextManager[McpSession]) -> None:
        self._session_cm = session_cm
        self._stop = asyncio.Event()
        self._started = asyncio.Event()
        self._session: McpSession | None = None
        self._enter_error: Exception | None = None
        self._exit_error: Exception | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> McpConnection:
        """在专用 task 中进入连接上下文；进入失败即清理并抛出底层原因。"""
        self._task = asyncio.create_task(self._run())
        try:
            await self._started.wait()
        except BaseException:
            await self._shutdown()
            raise
        if self._enter_error is not None:
            error, self._enter_error = self._enter_error, None
            await self._shutdown()
            raise error
        if self._session is None:
            await self._shutdown()
            raise RuntimeError("MCP connection runner stopped before establishing a session")
        return self

    async def list_tools(self) -> Sequence[McpToolDefinition]:
        return await self._require_session().list_tools()

    async def call_tool(self, name: str, arguments: Mapping[str, Any]) -> McpCallResult:
        return await self._require_session().call_tool(name, arguments)

    async def close(self) -> None:
        """关闭连接（幂等）：上下文退出发生在 runner task，close 可从任意 task 调用。"""
        await self._shutdown()
        if self._exit_error is not None:
            error, self._exit_error = self._exit_error, None
            raise error

    def _require_session(self) -> McpSession:
        if self._session is None:
            raise RuntimeError("MCP connection is closed")
        return self._session

    async def _run(self) -> None:
        try:
            self._session = await self._session_cm.__aenter__()
        except Exception as exc:
            self._enter_error = exc
            return
        finally:
            self._started.set()
        try:
            await self._stop.wait()
        finally:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception as exc:
                self._exit_error = exc

    async def _shutdown(self) -> None:
        task, self._task = self._task, None
        self._stop.set()
        if task is None:
            return
        done, _pending = await asyncio.wait({task}, timeout=_CLOSE_WAIT_SECONDS)
        if not done:
            task.cancel()
            done, _pending = await asyncio.wait({task}, timeout=_CLOSE_WAIT_SECONDS)
        # 显式取回 task 结果：吞掉 CancelledError（收尾本就是取消语义），其余异常
        # 记录到 _exit_error 供 close() 传播——绝不静默丢失（"exception never retrieved"）。
        for finished in done:
            exc = finished.exception() if not finished.cancelled() else None
            if exc is not None and self._exit_error is None:
                self._exit_error = exc

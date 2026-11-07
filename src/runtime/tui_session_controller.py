"""TUI 的会话控制器（ADR 0013）：共享 PluginHost/MCP，按会话产出 EngineRuntime。

放在 runtime 层而不是 TUI：控制器要持有存储与运行时装配，TUI 组件只消费事件流与
`SessionSummary`，不得直接 import 持久化模块（tests/tui/test_event_consumption.py）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from src.config.yaml_config import IntelliAgentConfig
from src.core.agent_events import EventSink
from src.core.engine import Engine
from src.core.plugin_host import PluginHost
from src.plugins.storage import StorageStore
from src.runtime.engine_runtime import EngineRuntime, build_engine_runtime, storage_store
from src.runtime.plugin_assembly import (
    build_host,
    connect_mcp_plugins,
    create_llm_client,
    permission_warning,
)
from src.runtime.session import SessionSelection, ensure_conversation_title, new_conversation_id, resolve_session
from src.runtime.session_view import SessionSummary

TUI_SESSION_PREFIX = "tui"
"""新建会话 id 的前缀（ADR 0013：``tui-{uuid4().hex}``）。"""


class TuiSessionController:
    """一次装配共享 PluginHost/MCP，按需产出不同会话的 EngineRuntime。

    每个 EngineRuntime 的 Engine 自带内存 Conversation 与 Compactor，换实例即换会话；
    因此切换无需 Engine 提供重置入口，也不破坏 append-only 单会话的设计前提。
    """

    def __init__(
        self,
        config: IntelliAgentConfig,
        workspace: Path,
        model: str,
        model_label: str,
        *,
        resume_last: bool,
        conversation_id: str | None,
        notices: list[str],
    ) -> None:
        self._config = config
        self._workspace = workspace
        self._model = model
        self._model_label = model_label
        self._resume_last = resume_last
        self._startup_conversation_id = conversation_id
        self._notices = notices
        self._llm = create_llm_client(config)
        self._host: PluginHost | None = None
        self._storage: StorageStore | None = None
        self._mcp_closers: list[Callable[[], Awaitable[None]]] = []
        self._runtimes: list[EngineRuntime] = []
        self._current: SessionSelection | None = None
        self._engine: Engine | None = None

    @property
    def model_label(self) -> str:
        """状态栏展示用的模型名（配置里的 name，缺失时回退 Model Ref）。"""
        return self._model_label

    async def initial_runner(self, sink: EventSink) -> Engine:
        """首次装配：建 host + MCP，解析启动会话并产出 Engine。"""
        host = build_host(self._config)
        plugins = await connect_mcp_plugins(self._config, host)
        self._host = host
        self._storage = storage_store(host)
        self._mcp_closers = [plugin.close for plugin in plugins]
        warning = permission_warning(host)
        if warning is not None:
            self._notices.append(warning.strip())
        selection = await resolve_session(
            self._storage,
            workspace=str(self._workspace),
            prefix=TUI_SESSION_PREFIX,
            resume_last=self._resume_last,
            conversation_id=self._startup_conversation_id,
        )
        return self._activate(sink, selection)

    async def list_sessions(self) -> tuple[SessionSummary, ...]:
        """本 workspace 下的会话列表（按创建时间倒序）。"""
        if self._storage is None:
            return ()
        records = await self._storage.list_conversations(workspace=str(self._workspace))
        return tuple(
            SessionSummary(entry_id=record.entry_id, title=record.title, created_at=record.created_at)
            for record in records
        )

    async def open(self, sink: EventSink, conversation_id: str) -> Engine:
        """打开既有会话：续接其最新 leaf。"""
        selection = await resolve_session(
            self._storage,
            workspace=str(self._workspace),
            prefix=TUI_SESSION_PREFIX,
            conversation_id=conversation_id,
        )
        return self._activate(sink, selection)

    async def create(self, sink: EventSink) -> Engine:
        """新建一段会话并切换过去。"""
        selection = SessionSelection(conversation_id=new_conversation_id(TUI_SESSION_PREFIX), resume=False)
        if self._storage is not None:
            await self._storage.ensure_conversation(selection.conversation_id, workspace=str(self._workspace))
        return self._activate(sink, selection)

    async def ensure_title(self) -> str | None:
        """为当前会话生成标题（幂等）：首轮收束后调用。"""
        if self._storage is None or self._current is None or self._engine is None:
            return None
        return await ensure_conversation_title(
            self._llm,
            self._storage,
            conversation_id=self._current.conversation_id,
            messages=self._engine.messages,
            model=self._model,
        )

    async def close(self) -> None:
        """释放 MCP 连接与存储连接；各 runtime 不单独关闭（切换时已丢弃引用）。"""
        first_error: Exception | None = None
        for closer in self._mcp_closers:
            try:
                await closer()
            except Exception as exc:
                first_error = first_error or exc
        if self._storage is not None:
            try:
                await self._storage.close()
            except Exception as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error

    def _activate(self, sink: EventSink, selection: SessionSelection) -> Engine:
        """按选中会话造一个 EngineRuntime 并记下它，返回其 Engine 作为 TaskRunner。"""
        if self._host is None:
            raise RuntimeError("会话控制器尚未完成首次装配")
        runtime = build_engine_runtime(
            self._config,
            self._host,
            self._llm,
            self._model,
            sink,
            conversation_id=selection.conversation_id,
            resume=selection.resume,
            # MCP/存储由本控制器的 close 统一释放：runtime 自身不持有关闭责任。
            closers=(),
        )
        self._runtimes.append(runtime)
        self._current = selection
        self._engine = runtime.engine
        return runtime.engine

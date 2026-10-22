"""Engine 运行时装配：把压缩、持久化与 usage 计数接到 PluginHost 上（P0）。

职责边界：
- 本模块是组合根的一部分，负责把 storage 能力、Compactor hooks、TokenCounter 与 Engine 接起来；
- core 仍只认注入的 LLMClient / hook / sink，不反向依赖 storage 或 runtime；
- 一个 database_url 可以承载多段会话：TUI 固定续接自己的会话根，headless 每次新建会话根。

存储插件缺席时（plugins.storage.enabled: false）不接压缩与持久化，保持“能力缺席即功能缺席”。
context 未配置时仍持久化，但跳过阈值压缩（Compactor.should_compact 返回 False）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from src.config.yaml_config import IntelliAgentConfig
from src.core.agent_events import EventSink
from src.core.compaction import Compactor
from src.core.engine import Engine
from src.core.plugin_host import CapabilityKind, PluginHost
from src.core.token_counting import TokenCounter, UsageRecordingClient
from src.core.turn_hooks import TurnHookProvider
from src.llm.stream import LLMClient
from src.plugins.storage import STORAGE_CAPABILITY_NAME, StorageStore


@dataclass
class EngineRuntime:
    """一次前端运行所需的 Engine 与其可选资源依赖。"""

    engine: Engine
    storage: StorageStore | None = None
    closers: tuple[Callable[[], Awaitable[None]], ...] = ()

    async def close(self) -> None:
        """释放 MCP 等外部资源，再释放存储连接；重复关闭幂等。"""
        first_error: Exception | None = None
        for closer in self.closers:
            try:
                await closer()
            except Exception as exc:
                first_error = first_error or exc
        if self.storage is not None:
            try:
                await self.storage.close()
            except Exception as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error


def build_engine_runtime(
    config: IntelliAgentConfig,
    host: PluginHost,
    llm: LLMClient,
    model: str,
    sink: EventSink | None,
    *,
    conversation_id: str,
    resume: bool,
    closers: Sequence[Callable[[], Awaitable[None]]] = (),
) -> EngineRuntime:
    """按配置与插件宿主组装 EngineRuntime。

    Args:
        config: 已校验的 YAML 配置（读取 limit.context）。
        host: 已加载插件的宿主（读取 tool/hook/storage 能力）。
        llm: 原始模型客户端；压缩摘要直接使用它，会话请求使用 usage 记录装饰器。
        model: 引擎与压缩共用的 Model Ref。
        sink: 事件出口；None 表示不订阅事件。
        conversation_id: 会话根 entry id；同一 id 的 TUI 重启后续接同一段会话。
        resume: True 续接该会话的最新 leaf；False 要求该会话是全新的（headless 每次新 id）。
        closers: 运行结束时释放的外部资源（如 MCP 插件 close）。
    """
    storage = _storage_store(host)
    hooks: list[TurnHookProvider] = []
    client: LLMClient = llm
    if storage is not None:
        counter = TokenCounter()
        client = UsageRecordingClient(llm, counter)
        compactor = Compactor(
            llm,
            storage,
            model=model,
            counter=counter,
            context_window=_context_window(config, model),
            conversation_root_id=conversation_id,
            resume=resume,
        )
        hooks.extend(compactor.hooks())
    engine = Engine.from_host(host, llm=client, model=model, sink=sink, extra_hooks=hooks)
    return EngineRuntime(engine=engine, storage=storage, closers=tuple(closers))


def _storage_store(host: PluginHost) -> StorageStore | None:
    """读取内置 storage 能力；未启用时返回 None。"""
    provider = host.capabilities(CapabilityKind.STORAGE).get(STORAGE_CAPABILITY_NAME)
    if provider is None:
        return None
    if not isinstance(provider, StorageStore):
        raise TypeError(
            f"storage capability '{STORAGE_CAPABILITY_NAME}' must provide StorageStore, got {type(provider).__name__}"
        )
    return provider


def _context_window(config: IntelliAgentConfig, model: str) -> int | None:
    """从配置读取模型 context 上限；未声明时返回 None（只持久化、不自动压缩）。"""
    provider_name, _, model_id = model.partition("/")
    provider = config.providers.get(provider_name)
    if provider is None:
        return None
    entry = provider.models.get(model_id)
    return entry.limit.context if entry is not None else None

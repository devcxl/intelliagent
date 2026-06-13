#!/usr/bin/env python3
"""AgentRuntime — 管理 LLM 客户端和引擎的创建与复用。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from src.core.react_engine import ReactEngine
from src.types.permission import (
    LLMClientProtocol,
    PermissionCallbackProtocol,
    PermissionEngineProtocol,
)

if TYPE_CHECKING:
    from src.config.unified_config import UnifiedConfig


class AgentRuntime:
    """Agent 运行时 — 单例管理 LLM 客户端，每次创建独立 ReactEngine。

    支持两种构造方式：
    - AgentRuntime(settings=...) — 旧版 Settings / SimpleNamespace（向后兼容）
    - AgentRuntime(config=UnifiedConfig(...)) — 新版统一配置
    """

    def __init__(
        self,
        settings: Any = None,
        *,
        config: UnifiedConfig | None = None,
        llm_client_factory: Callable[[], LLMClientProtocol] | None = None,
        permission_engine_factory: Callable[[], PermissionEngineProtocol] | None = None,
        permission_callback_factory: Callable[[], PermissionCallbackProtocol] | None = None,
    ) -> None:
        self._settings = settings
        self._config = config
        self._llm_client_factory = llm_client_factory or self._default_llm_client_factory
        self._permission_engine_factory = permission_engine_factory or self._default_permission_engine_factory
        self._permission_callback_factory = permission_callback_factory or self._default_permission_callback_factory
        self._llm_client: LLMClientProtocol | None = None

    # ------------------------------------------------------------------
    # 默认工厂（保持向后兼容行为）
    # ------------------------------------------------------------------

    def _default_llm_client_factory(self) -> LLMClientProtocol:
        from src.llm.llm_client import LLMClient

        if self._config is not None:
            llm = self._config.llm
            return LLMClient(
                api_key=llm.api_key,
                base_url=llm.base_url,
                model=llm.model,
            )

        return LLMClient(
            api_key=getattr(self._settings, "OPENAI_API_KEY", None),
            base_url=getattr(self._settings, "OPENAI_API_BASE", None),
            model=getattr(self._settings, "OPENAI_MODEL", "gpt-4o-mini"),
        )

    def _default_permission_engine_factory(self) -> PermissionEngineProtocol:
        from src.core.permission_engine import PermissionEngine, load_permission_engine

        if self._config is not None:
            rules = [r.model_dump() for r in self._config.permissions.rules]
            workspace = Path(self._config.workspace.dir)
            return PermissionEngine(rules=rules, workspace=workspace)

        workspace = Path(getattr(self._settings, "WORKSPACE_DIR", str(Path.cwd())))
        config_path = getattr(self._settings, "PERMISSION_CONFIG", "permissions.json")
        return load_permission_engine(str(config_path), workspace)

    def _default_permission_callback_factory(self) -> PermissionCallbackProtocol:
        from src.runtime.permission_callback import CliCallback

        return CliCallback(timeout=120.0)

    # ------------------------------------------------------------------
    # 公共方法
    # ------------------------------------------------------------------

    def get_llm_client(self) -> LLMClientProtocol:
        if self._llm_client is None:
            self._llm_client = self._llm_client_factory()
        return self._llm_client

    def create_engine(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
    ) -> ReactEngine:
        llm = self.get_llm_client()
        permission_engine = self._permission_engine_factory()
        permission_callback = self._permission_callback_factory()
        return ReactEngine(
            llm_client=llm,
            max_iterations=max_iterations,
            permission_engine=permission_engine,
            permission_callback=permission_callback,
        )


__all__ = ["AgentRuntime"]

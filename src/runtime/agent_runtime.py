#!/usr/bin/env python3
"""AgentRuntime — 管理 LLM 客户端和引擎的创建与复用。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.llm.llm_client import LLMClient
from src.core.react_engine import ReactEngine


class AgentRuntime:
    """Agent 运行时 — 单例管理 LLM 客户端，每次创建独立 ReactEngine。"""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._llm_client: Any = None

    def get_llm_client(self) -> Any:
        if self._llm_client is None:
            self._llm_client = LLMClient(
                api_key=getattr(self._settings, "OPENAI_API_KEY", None),
                base_url=getattr(self._settings, "OPENAI_API_BASE", None),
                model=getattr(self._settings, "OPENAI_MODEL", "gpt-4o-mini"),
            )
        return self._llm_client

    def create_engine(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
    ) -> Any:
        from src.core.permission_engine import CliCallback, load_permission_engine

        llm = self.get_llm_client()

        workspace = Path(getattr(self._settings, "WORKSPACE_DIR", str(Path.cwd())))
        config_path = getattr(self._settings, "PERMISSION_CONFIG", "permissions.json")
        permission_engine = load_permission_engine(str(config_path), workspace)
        permission_callback = CliCallback(timeout=120.0)

        return ReactEngine(
            llm_client=llm,
            max_tokens=max_iterations or 10,
            permission_engine=permission_engine,
            permission_callback=permission_callback,
        )


__all__ = ["LLMClient", "ReactEngine", "AgentRuntime"]

from __future__ import annotations

from src.config.unified_config import UnifiedConfig
from src.types.llm import LLMClientProtocol


class LLMClientFactory:
    def __init__(self, config: UnifiedConfig) -> None:
        self._config = config

    def create(self) -> LLMClientProtocol:
        from src.llm.llm_client import LLMClient

        api_key = ""
        base_url = None
        model = self._config.model or ""

        provider_id = model.split("/", 1)[0] if "/" in model else None
        if provider_id and provider_id in self._config.provider:
            pc = self._config.provider[provider_id]
            if pc.options:
                api_key = pc.options.apiKey or ""
                base_url = pc.options.baseURL
        else:
            for pc in self._config.provider.values():
                if pc.options:
                    if pc.options.apiKey:
                        api_key = pc.options.apiKey
                    if pc.options.baseURL:
                        base_url = pc.options.baseURL

        return LLMClient(api_key=api_key, base_url=base_url, model=model)


__all__ = ["LLMClientFactory"]

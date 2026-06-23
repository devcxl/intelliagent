from __future__ import annotations

import json
import ssl
import urllib.request
from pathlib import Path
from typing import Any

from src.types.provider import Provider

CACHE_DIR = Path.home() / ".intelliagent"
CACHE_FILE = CACHE_DIR / "providers.json"
REGISTRY_URL = "https://models.dev/api.json"


class ProviderRegistry:
    """Provider 注册表 — 从 models.dev/api.json 加载 Provider/Model 元数据。

    默认从本地缓存加载，缓存不存在时从远程拉取。
    """

    _instance: dict[str, Provider] | None = None

    @classmethod
    def load(cls, force_refresh: bool = False) -> dict[str, Provider]:
        """加载注册表，返回 {provider_id: Provider} 映射。

        Args:
            force_refresh: 强制从远程拉取，忽略缓存

        Returns:
            解析后的 Provider 字典
        """
        if cls._instance is not None and not force_refresh:
            return cls._instance

        raw = cls._load_raw(force_refresh)
        providers: dict[str, Provider] = {}
        for pid, data in raw.items():
            providers[pid] = Provider(**data)

        cls._instance = providers
        return providers

    @classmethod
    def _load_raw(cls, force_refresh: bool = False) -> dict[str, Any]:
        if not force_refresh and CACHE_FILE.exists():
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))

        ctx = ssl.create_default_context()
        req = urllib.request.Request(REGISTRY_URL)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return data

    @classmethod
    def get_model_context_limit(cls, provider_id: str, model_id: str) -> int | None:
        """查 model.limit.context，查不到返回 None。"""
        providers = cls.load()
        provider = providers.get(provider_id)
        if not provider:
            return None
        model = provider.models.get(model_id)
        if not model or not model.limit:
            return None
        return model.limit.context

    @classmethod
    def clear_cache(cls) -> None:
        """清除内存缓存（测试用）。"""
        cls._instance = None


__all__ = [
    "ProviderRegistry",
    "CACHE_DIR",
    "CACHE_FILE",
    "REGISTRY_URL",
]

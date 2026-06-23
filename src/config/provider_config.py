from __future__ import annotations

from pydantic import BaseModel

from src.types.provider import Cost, ModelLimit


class ProviderOptions(BaseModel):
    """Provider 级选项 — 对应 opencode ProviderConfig.options。"""

    apiKey: str | None = None
    baseURL: str | None = None
    timeout: int | None = None
    headers: dict[str, str] | None = None
    setCacheKey: bool | None = None


class ModelOverride(BaseModel):
    """模型级覆盖 — 在 provider 默认值之上叠加。"""

    id: str | None = None
    options: ProviderOptions | None = None
    limit: ModelLimit | None = None
    cost: Cost | None = None


class ProviderConfig(BaseModel):
    """用户配置的 Provider — 对应 opencode provider.<id> 配置块。"""

    name: str | None = None
    npm: str | None = None
    options: ProviderOptions | None = None
    models: dict[str, ModelOverride] | None = None


__all__ = [
    "ProviderOptions",
    "ModelOverride",
    "ProviderConfig",
]

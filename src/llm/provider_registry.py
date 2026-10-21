"""Model Ref 解析：`provider/model-id` → 运行时目标（协议、端点、密钥、限额）。

配置层与 llm 层的边界在这里显式转换：registry 只接收不可变的 ProviderSettings，
不导入 pydantic 配置模型。密钥在 resolve 时按 env 顺序读取环境变量，不落盘、不进日志。
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

_DEFAULT_APIS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}
_DEFAULT_ENVS: dict[str, tuple[str, ...]] = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


@dataclass(frozen=True)
class ModelSettings:
    """一个模型的运行时声明（由配置转换而来）。"""

    wire_model: str
    supports_tools: bool = True
    max_output_tokens: int | None = None
    context_window: int | None = None


@dataclass(frozen=True)
class ProviderSettings:
    """一个 provider 的运行时声明。"""

    protocol: str
    api_base: str | None = None
    env: tuple[str, ...] = ()
    models: Mapping[str, ModelSettings] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelTarget:
    """Model Ref 的解析结果：适配器据此构造请求。"""

    provider: str
    model_id: str
    wire_model: str
    protocol: str
    api_base: str | None
    api_key: str | None
    supports_tools: bool
    max_output_tokens: int | None
    context_window: int | None


class ModelRegistry:
    """Provider 声明表：把 Model Ref 解析为 ModelTarget。"""

    def __init__(self, providers: Mapping[str, ProviderSettings]) -> None:
        self._providers = dict(providers)

    def resolve(self, ref: str) -> ModelTarget:
        """解析 `provider/model-id`；未知 provider/model 或缺密钥时抛 ValueError。"""
        provider_name, separator, model_id = ref.partition("/")
        if not separator or not provider_name or not model_id:
            raise ValueError(f"模型引用必须是 provider/model-id 形式，实际为 {ref!r}")
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(f"未知 provider {provider_name!r}（providers 段未声明）")
        model = provider.models.get(model_id)
        if model is None:
            raise ValueError(f"provider {provider_name!r} 下没有模型 {model_id!r}")
        api_base = provider.api_base or _DEFAULT_APIS.get(provider.protocol)
        if not api_base:
            raise ValueError(f"provider {provider_name!r} 缺少 api（{provider.protocol} 协议必须显式声明）")
        env_names = provider.env or _DEFAULT_ENVS.get(provider.protocol, ())
        api_key = _first_env(env_names)
        if api_key is None and env_names:
            raise ValueError(
                f"provider {provider_name!r} 缺少 API Key：请设置环境变量 {' / '.join(env_names)}（或声明 env:）"
            )
        return ModelTarget(
            provider=provider_name,
            model_id=model_id,
            wire_model=model.wire_model,
            protocol=provider.protocol,
            api_base=api_base,
            api_key=api_key,
            supports_tools=model.supports_tools,
            max_output_tokens=model.max_output_tokens,
            context_window=model.context_window,
        )


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None

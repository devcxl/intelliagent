"""契约测试用的 fake 插件与 Manifest 构造辅助。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest

DEFAULT_CAPABILITIES: tuple[CapabilityDeclaration, ...] = (
    CapabilityDeclaration(kind=CapabilityKind.TOOL, name="fake.echo"),
)


class FakeToolConfig(BaseModel):
    """fake 插件的配置 schema：limit 必须是整数，禁止未知字段。"""

    model_config = ConfigDict(extra="forbid")

    limit: int = 10
    path: str = "."


def build_manifest(
    name: str = "fake-tool",
    *,
    api_version: int = 1,
    capabilities: Sequence[CapabilityDeclaration] = DEFAULT_CAPABILITIES,
    config_schema: type[BaseModel] | None = None,
) -> Manifest:
    """构造测试用 Manifest，version 固定为 0.1.0。"""
    return Manifest(
        name=name,
        version="0.1.0",
        api_version=api_version,
        capabilities=tuple(capabilities),
        config_schema=config_schema,
    )


class FakePlugin:
    """记录宿主传入内容的最小 Plugin 实现。

    providers 未给定时，为 Manifest 声明的每个能力注册占位提供者；给定空 dict 表示一个都不注册。
    """

    def __init__(
        self,
        manifest: Manifest | None = None,
        providers: Mapping[tuple[CapabilityKind, str], object] | None = None,
    ) -> None:
        self.manifest = manifest if manifest is not None else build_manifest()
        self.providers: dict[tuple[CapabilityKind, str], object] | None = (
            dict(providers) if providers is not None else None
        )
        self.received_config: BaseModel | None = None

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        self.received_config = config
        if self.providers is None:
            for declaration in self.manifest.capabilities:
                registrar.register(declaration.kind, declaration.name, object())
            return
        for (kind, name), provider in self.providers.items():
            registrar.register(kind, name, provider)


def single_provider() -> object:
    """opaque 能力提供者占位对象。"""
    return object()

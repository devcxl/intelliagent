"""经 Entry Points 发现路径使用的 fake 外部插件（模拟第三方包内的插件实现）。"""

from __future__ import annotations

from pydantic import BaseModel

from src.plugins import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest


class FakeExternalConfig(BaseModel):
    """fake-memory 插件的配置 schema。"""

    depth: int = 3


class FakeExternalPlugin:
    """模拟外部插件：Manifest 声明 tool + hook 两种能力。"""

    manifest = Manifest(
        name="fake-memory",
        version="1.2.3",
        api_version=1,
        capabilities=(
            CapabilityDeclaration(kind=CapabilityKind.TOOL, name="fake-memory.recall"),
            CapabilityDeclaration(kind=CapabilityKind.HOOK, name="fake-memory.inject"),
        ),
        config_schema=FakeExternalConfig,
    )

    def __init__(self) -> None:
        self.received_config: BaseModel | None = None

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        self.received_config = config
        registrar.register(CapabilityKind.TOOL, "fake-memory.recall", object())
        registrar.register(CapabilityKind.HOOK, "fake-memory.inject", object())


class FakeIncompatiblePlugin:
    """api_version 不在宿主支持区间内的外部插件，宿主必须拒绝加载。"""

    manifest = Manifest(
        name="fake-future",
        version="2.0.0",
        api_version=2,
        capabilities=(CapabilityDeclaration(kind=CapabilityKind.TOOL, name="fake-future.run"),),
    )

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        registrar.register(CapabilityKind.TOOL, "fake-future.run", object())


class NotAPlugin:
    """没有 Plugin 契约的对象，Entry Points 解析必须拒绝。"""


class UnrelatedFactory:
    """非工厂、非插件的可调用对象（构造需要参数）。"""

    def __init__(self, required_arg: str) -> None:
        self.required_arg = required_arg


def create_fake_external_plugin() -> FakeExternalPlugin:
    """工厂函数形态的 Entry Point 值。"""
    return FakeExternalPlugin()


fake_external_plugin_instance = FakeExternalPlugin()

not_a_plugin = NotAPlugin()

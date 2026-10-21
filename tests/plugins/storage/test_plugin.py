"""storage 内置插件经 PluginHost 注册 STORAGE 能力的契约测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.core.plugin_host import CapabilityKind, PluginConfigError, PluginHost
from src.plugins.storage import StoragePlugin, StorageStore


async def test_storage_plugin_registers_storage_capability(tmp_path: Path) -> None:
    host = PluginHost()
    loaded = host.load(StoragePlugin(), {"database_url": str(tmp_path / "plugin.db")})

    provider = host.get_capability(CapabilityKind.STORAGE, "sqlite")

    assert loaded.manifest.name == "storage"
    assert isinstance(provider, StorageStore)
    assert dict(host.capabilities(CapabilityKind.STORAGE)) == {"sqlite": provider}
    try:
        entry = await provider.append_entry("message", {"n": 1})
        assert await provider.get_entry(entry.id) == entry
    finally:
        await provider.close()


async def test_storage_plugin_default_config_registers_provider() -> None:
    host = PluginHost()

    host.load(StoragePlugin())

    provider = host.get_capability(CapabilityKind.STORAGE, "sqlite")
    assert isinstance(provider, StorageStore)
    await provider.close()


def test_storage_plugin_rejects_unknown_config_fields() -> None:
    with pytest.raises(PluginConfigError, match="bogus"):
        PluginHost().load(StoragePlugin(), {"bogus": 1})


def test_register_rejects_wrong_config_type() -> None:
    """错误配置类型必须显式报错，不得静默回退默认值（PR #70 审查 Standards medium）。"""
    from pydantic import BaseModel

    from src.core.plugin_host import CapabilityRegistrar

    class WrongConfig(BaseModel):
        pass

    plugin = StoragePlugin()
    registrar = CapabilityRegistrar(plugin.manifest.name, plugin.manifest)
    with pytest.raises(TypeError, match="StorageConfig"):
        plugin.register(registrar, WrongConfig())

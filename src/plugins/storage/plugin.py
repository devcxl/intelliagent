"""storage 内置插件：以 STORAGE 能力注册 SQLite append-only 存储（ADR 0007 / ADR 0010）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest
from src.plugins.storage.store import StorageStore

STORAGE_CAPABILITY_NAME = "sqlite"


class StorageConfig(BaseModel):
    """storage 插件配置：SQLite URL 或数据库文件路径。"""

    model_config = ConfigDict(extra="forbid")

    database_url: str = "sqlite:///intelliagent.db"


class StoragePlugin:
    """storage 内置插件：注册 STORAGE 能力，提供 append-only 的 entry 存储。"""

    manifest = Manifest(
        name="storage",
        version="0.1.0",
        api_version=1,
        capabilities=(CapabilityDeclaration(kind=CapabilityKind.STORAGE, name=STORAGE_CAPABILITY_NAME),),
        config_schema=StorageConfig,
    )

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        if config is not None and not isinstance(config, StorageConfig):
            raise TypeError(f"storage plugin expects StorageConfig, got {type(config).__name__}")
        settings = config if config is not None else StorageConfig()
        registrar.register(CapabilityKind.STORAGE, STORAGE_CAPABILITY_NAME, StorageStore(settings.database_url))

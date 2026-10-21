"""Plugin 协议：进程内 Python 组件，声明 Manifest 并注册能力。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from src.plugins.manifest import Manifest
from src.plugins.registry import CapabilityRegistrar


@runtime_checkable
class Plugin(Protocol):
    """插件契约（CONTEXT 术语：Plugin）。

    宿主读取 manifest 后做 api_version 门禁与配置校验，再调用 register 注册能力。
    """

    manifest: Manifest

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        """把 Manifest 声明的全部能力注册到 registrar。

        config 是经 Manifest config_schema 校验后的插件配置；未声明 config_schema 时为 None。
        """
        ...

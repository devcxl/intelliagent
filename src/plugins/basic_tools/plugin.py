"""内置基本工具插件：一个能力包，注册 read / write / bash / edit / grep 五个 Tool Capability。"""

from __future__ import annotations

from pydantic import BaseModel

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest
from src.plugins.basic_tools.bash_tool import bash_tool
from src.plugins.basic_tools.file_tools import edit_tool, read_tool, write_tool
from src.plugins.basic_tools.grep_tool import grep_tool
from src.utils.path_policy import PathPolicy

TOOL_NAMES = ("read", "write", "bash", "edit", "grep")


class BasicToolsPlugin:
    """CONTEXT 术语：Built-in Plugin——与外部插件走同一注册契约，区别仅在发现方式（ADR 0007）。"""

    def __init__(self, path_policy: PathPolicy | None = None) -> None:
        self._path_policy = path_policy
        self.manifest = Manifest(
            name="basic-tools",
            version="0.1.0",
            api_version=1,
            capabilities=tuple(CapabilityDeclaration(kind=CapabilityKind.TOOL, name=name) for name in TOOL_NAMES),
        )

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        """把 Manifest 声明的五个工具全部注册为 Tool Capability 提供者（ToolSpec）。"""
        specs = (
            read_tool(self._path_policy),
            write_tool(self._path_policy),
            bash_tool(),
            edit_tool(self._path_policy),
            grep_tool(self._path_policy),
        )
        for spec in specs:
            registrar.register(CapabilityKind.TOOL, spec.name, spec)

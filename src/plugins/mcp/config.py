"""mcp 插件配置：服务器列表与连接参数（传输类型显式声明，不靠错误字符串嗅探）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SERVER_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
"""服务器名是能力名 mcp_{server}_{tool} 的组成部分，须满足 Capability 命名约束的子集。"""


class McpServerConfig(BaseModel):
    """单个 MCP 服务器配置。

    transport 显式声明接入方式（stdio / streamable_http / sse）；旧实现按 "405" 字符串嗅探回退 SSE，
    显式声明后不再有隐式切换。connect_timeout 封顶「连接 + 工具发现」整体耗时（秒），绝不无限等待。
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=SERVER_NAME_PATTERN)
    transport: Literal["stdio", "streamable_http", "sse"] = "stdio"
    command: list[str] = Field(default_factory=list)
    url: str = ""
    headers: dict[str, str] | None = None
    env: dict[str, str] | None = None
    cwd: str | None = None
    timeout: float = 5.0
    sse_read_timeout: float = 300.0
    connect_timeout: float = Field(default=30.0, gt=0)

    @model_validator(mode="after")
    def _require_transport_fields(self) -> McpServerConfig:
        if self.transport == "stdio":
            if not self.command:
                raise ValueError(f"MCP server '{self.name}': transport 'stdio' requires a non-empty command")
            if self.url:
                raise ValueError(f"MCP server '{self.name}': transport 'stdio' must not set url")
        else:
            if not self.url:
                raise ValueError(f"MCP server '{self.name}': transport '{self.transport}' requires url")
            if self.command:
                raise ValueError(f"MCP server '{self.name}': transport '{self.transport}' must not set command")
        return self


class McpPluginConfig(BaseModel):
    """mcp 插件配置：server 列表；名称唯一（能力名的组成部分，重名会掩盖来源）。"""

    model_config = ConfigDict(extra="forbid")

    servers: list[McpServerConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_unique_server_names(self) -> McpPluginConfig:
        seen: set[str] = set()
        for server in self.servers:
            if server.name in seen:
                raise ValueError(f"duplicate MCP server name '{server.name}'")
            seen.add(server.name)
        return self

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """单个 MCP 服务器配置。"""

    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None


class MCPConfig(BaseModel):
    """MCP 客户端配置 — 从 UnifiedConfig 或 dict 构造。"""

    servers: list[MCPServerConfig] = Field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPConfig:
        return cls.model_validate(data)

    @classmethod
    def from_unified_config(cls, data: dict[str, Any]) -> MCPConfig:
        """从 UnifiedConfig.mcp 字典构造 MCPConfig。

        data 是 UnifiedConfig 中 mcp 字段的值（dict），
        应包含可选的 "servers" 键。
        """
        servers = data.get("servers", [])
        return cls.model_validate({"servers": servers})

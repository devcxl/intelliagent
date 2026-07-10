from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """单个 MCP 服务器配置。

    格式为 key-value，key 是服务器名称：
      { "server_name": { "command": ["uvx", "server-pkg"], "env": {...} } }
      或
      { "server_name": { "url": "https://...", "headers": {...} } }

    Attributes:
        name: 服务器名称（配置字典的 key）
        command: stdio 模式命令行（数组，第一个元素是命令，后续是参数）
        url: 远程服务器 URL
        headers: HTTP 头
        timeout: 超时时间（秒）
        sse_read_timeout: SSE 读取超时（秒）
        env: 注入到子进程的环境变量
        cwd: 子进程工作目录
    """

    name: str
    command: list[str] = Field(default_factory=list)
    url: str = ""
    headers: dict[str, str] | None = None
    timeout: float = 5.0
    sse_read_timeout: float = 300.0
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

        data 格式为 { "server_name": { "command": [...], ... }, ... }。
        """
        servers = []
        for name, cfg in data.items():
            servers.append(MCPServerConfig(name=name, **cfg))
        return cls.model_validate({"servers": servers})

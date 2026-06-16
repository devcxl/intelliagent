from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """单个 MCP 服务器配置。

    Attributes:
        name: 服务器名称，用于日志和工具名前缀
        transport: 传输方式，stdio（本地子进程）或 sse（远程 HTTP）
        command: stdio 模式：启动命令（如 npx、uvx）
        args: stdio 模式：命令行参数
        url: SSE 模式：远程服务器 URL
        headers: SSE 模式：自定义 HTTP 头
        timeout: SSE 模式：HTTP 超时时间（秒）
        sse_read_timeout: SSE 模式：SSE 读取超时（秒）
        env: 注入到子进程的环境变量
        cwd: 子进程工作目录
    """

    name: str
    transport: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
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
        """从原始字典构造 MCPConfig。

        Args:
            data: 包含 servers 键的字典，格式与 intelliagent.json 中 mcp 字段一致

        Returns:
            校验后的 MCPConfig 实例
        """
        return cls.model_validate(data)

    @classmethod
    def from_unified_config(cls, data: dict[str, Any]) -> MCPConfig:
        """从 UnifiedConfig.mcp 字典构造 MCPConfig。

        data 是 UnifiedConfig 中 mcp 字段的值（dict），
        应包含可选的 "servers" 键。
        """
        servers = data.get("servers", [])
        return cls.model_validate({"servers": servers})

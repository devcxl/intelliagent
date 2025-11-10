#!/usr/bin/env python3
"""
配置管理模块
加载环境变量（当前仅用于日志与 MCP 服务配置）
"""
import os
from dotenv import load_dotenv

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
MCP_SERVER_COMMAND = os.getenv("MCP_SERVER_COMMAND", "python3")
MCP_SERVER_SCRIPT = os.getenv("MCP_SERVER_SCRIPT", "mcp_server.py")

# 预留：未来可添加更多可配置项，如缓存目录等

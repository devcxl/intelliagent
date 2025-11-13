#!/usr/bin/env python3
"""
配置管理模块
加载环境变量（日志、MCP服务、OpenAI等配置）
"""
import os
from dotenv import load_dotenv

load_dotenv()

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# MCP 服务配置
MCP_SERVER_COMMAND = os.getenv("MCP_SERVER_COMMAND", "python3")
MCP_SERVER_SCRIPT = os.getenv("MCP_SERVER_SCRIPT", "mcp_server.py")

# OpenAI 配置
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# PDCA 配置
MAX_PDCA_CYCLES = int(os.getenv("MAX_PDCA_CYCLES", "3"))
MAX_RETRY_PER_STEP = int(os.getenv("MAX_RETRY_PER_STEP", "3"))

# 经验保存配置
EXPERIENCE_FILE = os.getenv("EXPERIENCE_FILE", "experiences.json")

# 预留：未来可添加更多可配置项

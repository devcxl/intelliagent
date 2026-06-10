#!/usr/bin/env python3
"""
兼容配置模块。

历史代码仍会从 `utils.config` 读取常量，PR1 先保留兼容层，统一配置来源改为
`src.config.settings.Settings`。
"""

from src.config import get_settings


settings = get_settings()

LOG_LEVEL = settings.LOG_LEVEL
MCP_CONFIG_FILE = settings.MCP_CONFIG_FILE

OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_API_BASE = settings.OPENAI_API_BASE
OPENAI_MODEL = settings.OPENAI_MODEL

MAX_PDCA_CYCLES = settings.MAX_PDCA_CYCLES
MAX_RETRY_PER_STEP = settings.MAX_RETRY_PER_STEP

EXPERIENCE_FILE = settings.EXPERIENCE_FILE

WEB_HOST = settings.WEB_HOST
WEB_PORT = settings.WEB_PORT
WEB_ENV = settings.WEB_ENV

DATABASE_URL = settings.DATABASE_URL

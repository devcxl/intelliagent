#!/usr/bin/env python3
"""
脱敏模块 — 对文本中的敏感信息（API Key、密码、Token、URL 凭据等）进行脱敏处理。
"""

from __future__ import annotations

import re

# 脱敏正则模式列表：(pattern, replacement)
# - 带捕获组的模式：保留捕获组前缀，敏感部分替换为 [REDACTED]
# - 不带捕获组的模式：整体替换为 [REDACTED]
_SECRET_PATTERNS: list[tuple[str, str]] = [
    (r"sk-[A-Za-z0-9_-]+", "[REDACTED]"),
    (r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]"),
    (r"(?i)(password\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]"),
    (r"(?i)(api_key\s*[=:]\s*)[^\s,;]+", r"\1[REDACTED]"),
    (r"(?i)(https?://[^:]+:)[^@]+@", r"\1[REDACTED]@"),
]


def redact_secrets(value: str) -> str:
    """对文本中的敏感信息进行脱敏处理。

    支持 OpenAI API Key（sk- 开头）、Bearer Token、密码、API Key、URL 凭据等模式。
    对于带捕获组的模式，保留捕获组前缀，将匹配的敏感部分替换为 [REDACTED]。
    对于不带捕获组的模式，将整个匹配替换为 [REDACTED]。

    Args:
        value: 原始文本

    Returns:
        脱敏后的文本
    """
    redacted = value
    for pattern, replacement in _SECRET_PATTERNS:
        redacted = re.sub(pattern, replacement, redacted)
    return redacted

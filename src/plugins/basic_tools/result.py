"""工具结果信封：所有工具返回统一 JSON 语义，status 真实、错误可诊断。"""

from __future__ import annotations

import json
from typing import Any

MAX_RESULT_CHARS = 50_000


def tool_success(**fields: Any) -> str:
    """成功信封：status="ok" 加工具自定义字段。"""
    return json.dumps({"status": "ok", **fields}, ensure_ascii=False)


def tool_error(code: str, error: str, **fields: Any) -> str:
    """错误信封：status="error" 加机器可读 code、人类可读 error 与诊断字段。"""
    return json.dumps({"status": "error", "code": code, "error": error, **fields}, ensure_ascii=False)

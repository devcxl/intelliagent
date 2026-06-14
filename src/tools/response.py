import json
from typing import Any, Dict


def success_response(data: Dict[str, Any]) -> str:
    """构建成功响应 JSON 字符串。

    Args:
        data: 要包含在响应中的额外键值对，会自动添加 status="ok"

    Returns:
        JSON 格式的成功响应字符串
    """
    return json.dumps({"status": "ok", **data}, ensure_ascii=False)


def error_response(error: str, code: str = "UNKNOWN_ERROR") -> str:
    """构建错误响应 JSON 字符串。

    Args:
        error: 错误描述信息
        code: 错误码，默认 "UNKNOWN_ERROR"

    Returns:
        JSON 格式的错误响应字符串
    """
    return json.dumps({"status": "error", "error": error, "code": code}, ensure_ascii=False)

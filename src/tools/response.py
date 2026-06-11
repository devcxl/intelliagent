import json
from typing import Dict, Any


def success_response(data: Dict[str, Any]) -> str:
    return json.dumps({"status": "ok", **data}, ensure_ascii=False)


def error_response(error: str, code: str = "UNKNOWN_ERROR") -> str:
    return json.dumps({"status": "error", "error": error, "code": code}, ensure_ascii=False)

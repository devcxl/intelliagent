"""仓储层共享工具 — 时间戳和 UUID 生成。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())

"""仓储层共享工具 — 时间戳、UUID 生成以及泛型 BaseRepository。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """泛型仓储基类，提供 save / get 公共实现。"""

    def __init__(self, session: AsyncSession, model_cls: type[ModelT]) -> None:
        self._session = session
        self._model_cls = model_cls

    async def save(self, obj: ModelT) -> ModelT:
        self._session.add(obj)
        await self._session.commit()
        return obj

    async def get(self, id: str) -> ModelT | None:
        return await self._session.get(self._model_cls, id)


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())

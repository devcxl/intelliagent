"""TaskRepository — tasks 表 CRUD，ID 使用 UUID。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Task
from src.db.repositories._utils import BaseRepository, now


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Task)

    async def list_by_conversation(self, conversation_id: str) -> list[Task]:
        result = await self._session.execute(
            select(Task)
            .where(Task.conversation_id == conversation_id)
            .order_by(Task.sort_order.asc(), Task.created_at.asc())
        )
        return list(result.scalars())

    async def update(
        self,
        task_id: str,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        sort_order: int | None = None,
    ) -> bool:
        task = await self._session.get(Task, task_id)
        if task is None:
            return False
        if title is not None:
            task.title = title
        if content is not None:
            task.content = content
        if status is not None:
            task.status = status
            if status == "completed":
                task.completed_at = now()
        if priority is not None:
            task.priority = priority
        if sort_order is not None:
            task.sort_order = sort_order
        task.updated_at = now()
        await self._session.commit()
        return True

    async def delete_by_conversation(self, conversation_id: str) -> None:
        result = await self._session.execute(select(Task).where(Task.conversation_id == conversation_id))
        for task in result.scalars():
            await self._session.delete(task)
        await self._session.commit()

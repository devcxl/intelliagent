"""TaskRepository — tasks 表 CRUD，ID 使用 UUID。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Task
from src.db.repositories._utils import now


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, task: Task) -> dict[str, Any]:
        self._session.add(task)
        await self._session.commit()
        return {"id": task.id, "status": task.status}

    async def get(self, task_id: str) -> dict[str, Any] | None:
        task = await self._session.get(Task, task_id)
        if task is None:
            return None
        return {
            "id": task.id,
            "conversation_id": task.conversation_id,
            "title": task.title,
            "content": task.content,
            "parent_id": task.parent_id,
            "status": task.status,
            "priority": task.priority,
            "sort_order": task.sort_order,
            "created_at": task.created_at.isoformat() if task.created_at else "",
            "updated_at": task.updated_at.isoformat() if task.updated_at else "",
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    async def list_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Task)
            .where(Task.conversation_id == conversation_id)
            .order_by(Task.sort_order.asc(), Task.created_at.asc())
        )
        return [
            {
                "id": t.id,
                "conversation_id": t.conversation_id,
                "title": t.title,
                "content": t.content,
                "parent_id": t.parent_id,
                "status": t.status,
                "priority": t.priority,
                "sort_order": t.sort_order,
                "created_at": t.created_at.isoformat() if t.created_at else "",
                "updated_at": t.updated_at.isoformat() if t.updated_at else "",
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in result.scalars()
        ]

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

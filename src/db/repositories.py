"""ORM 仓储类 — 基于 SQLAlchemy AsyncSession。"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Conversation, Message, Task


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


# ID 生成器
_msg_id_counter = 0
_msg_id_lock = threading.Lock()


def _next_msg_id() -> str:
    global _msg_id_counter
    with _msg_id_lock:
        _msg_id_counter += 1
        return f"msg-{_now_ts()}-{_msg_id_counter:04d}"


_task_id_counter = 0
_task_id_lock = threading.Lock()


def _next_task_id() -> str:
    global _task_id_counter
    with _task_id_lock:
        _task_id_counter += 1
        return f"task-{_now_ts()}-{_task_id_counter:04d}"


# ======================================================================
# ConversationRepository
# ======================================================================
class ConversationRepository:
    """conversations 表 CRUD — 基于 ORM。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        conversation_id: str,
        title: str = "",
        task: str = "",
        status: str = "idle",
    ) -> dict[str, Any]:
        conv = Conversation(id=conversation_id, title=title, task=task, status=status)
        self._session.add(conv)
        await self._session.commit()
        return {"id": conversation_id, "logs": []}

    async def get(self, conversation_id: str) -> dict[str, Any] | None:
        conv = await self._session.get(Conversation, conversation_id)
        if conv is None:
            return None
        return {
            "id": conv.id,
            "title": conv.title,
            "task": conv.task,
            "status": conv.status,
            "created_at": conv.created_at.isoformat() if conv.created_at else "",
            "updated_at": conv.updated_at.isoformat() if conv.updated_at else "",
            "logs": [],
        }

    async def update(
        self,
        conversation_id: str,
        title: str | None = None,
        status: str | None = None,
        logs: list[dict[str, Any]] | None = None,
    ) -> bool:
        conv = await self._session.get(Conversation, conversation_id)
        if conv is None:
            return False
        if title is not None:
            conv.title = title
        if status is not None:
            conv.status = status
        conv.updated_at = _now()
        await self._session.commit()
        return True

    async def delete(self, conversation_id: str) -> bool:
        conv = await self._session.get(Conversation, conversation_id)
        if conv is not None:
            await self._session.delete(conv)
            await self._session.commit()
        return True

    async def list_all(self) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Conversation).order_by(Conversation.updated_at.desc())
        )
        return [
            {
                "id": conv.id,
                "title": conv.title,
                "task": conv.task,
                "status": conv.status,
                "created_at": conv.created_at.isoformat() if conv.created_at else "",
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else "",
            }
            for conv in result.scalars()
        ]

    async def get_latest(self) -> dict[str, Any] | None:
        conversations = await self.list_all()
        return conversations[0] if conversations else None


# ======================================================================
# MessageRepository
# ======================================================================
class MessageRepository:
    """messages 表 CRUD — 基于 ORM。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, conversation_id: str, role: str, content: str) -> str:
        msg_id = _next_msg_id()
        msg = Message(id=msg_id, conversation_id=conversation_id, role=role, content=content)
        self._session.add(msg)
        await self._session.commit()
        return msg_id

    async def list_by_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else "",
            }
            for msg in result.scalars()
        ]


# ======================================================================
# TaskRepository
# ======================================================================
class TaskRepository:
    """tasks 表 CRUD — 基于 ORM。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        conversation_id: str,
        title: str,
        content: str = "",
        parent_id: str | None = None,
        priority: str = "medium",
        sort_order: int = 0,
    ) -> dict[str, Any]:
        task_id = _next_task_id()
        task = Task(
            id=task_id,
            conversation_id=conversation_id,
            title=title,
            content=content,
            parent_id=parent_id,
            priority=priority,
            sort_order=sort_order,
        )
        self._session.add(task)
        await self._session.commit()
        return {"id": task_id, "status": "pending"}

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
                task.completed_at = _now()
        if priority is not None:
            task.priority = priority
        if sort_order is not None:
            task.sort_order = sort_order
        task.updated_at = _now()
        await self._session.commit()
        return True

    async def delete_by_conversation(self, conversation_id: str) -> None:
        result = await self._session.execute(
            select(Task).where(Task.conversation_id == conversation_id)
        )
        for task in result.scalars():
            await self._session.delete(task)
        await self._session.commit()

"""任务管理工具 — task_write / task_add / task_update / task_finish。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Task
from src.db.repositories import TaskRepository
from src.db.repositories._utils import new_uuid
from src.utils.logger import logger

from .response import error_response, success_response

SessionFactoryProvider = Callable[[], async_sessionmaker[AsyncSession]]
ConversationIdProvider = Callable[[], str | None]


class TaskTools:
    """任务工具适配器，显式依赖 session factory 和当前 conversation。"""

    def __init__(
        self,
        session_factory_provider: SessionFactoryProvider,
        conversation_id_provider: ConversationIdProvider,
    ) -> None:
        self._session_factory_provider = session_factory_provider
        self._conversation_id_provider = conversation_id_provider

    def _conversation_id(self) -> str | None:
        return self._conversation_id_provider()

    def _context_error(self) -> str:
        return error_response("任务系统未初始化，缺少 Conversation 上下文", "CONTEXT_NOT_INITIALIZED")

    async def task_write(self, tasks: str) -> str:
        """批量创建任务。"""
        try:
            items = json.loads(tasks)
            if not isinstance(items, list):
                return error_response("tasks 必须是 JSON 数组", "INVALID_PARAMETERS")
        except json.JSONDecodeError as e:
            return error_response(f"tasks JSON 解析失败: {e}", "INVALID_PARAMETERS")

        conversation_id = self._conversation_id()
        if conversation_id is None:
            return self._context_error()

        async with self._session_factory_provider()() as session:
            repo = TaskRepository(session)
            existing = await repo.list_by_conversation(conversation_id)
            base_order = len(existing)

            created: list[dict[str, Any]] = []
            for idx, item in enumerate(items):
                if not isinstance(item, dict) or "title" not in item:
                    continue
                task = await repo.save(
                    Task(
                        id=new_uuid(),
                        conversation_id=conversation_id,
                        title=str(item["title"]),
                        content=str(item.get("content", "")),
                        parent_id=item.get("parent_id"),
                        priority=str(item.get("priority", "medium")),
                        sort_order=base_order + idx,
                    )
                )
                created.append({"id": task.id, "title": item["title"], "task_status": task.status})

        logger.debug("TaskTools - task_write | count=%d", len(created))
        return success_response({"tasks": created, "count": len(created)})

    async def task_add(
        self,
        title: str,
        content: str = "",
        priority: str = "medium",
        parent_id: str = "",
    ) -> str:
        """创建单条任务。"""
        title = title.strip()
        if not title:
            return error_response("title 不能为空", "EMPTY_TITLE")

        conversation_id = self._conversation_id()
        if conversation_id is None:
            return self._context_error()

        async with self._session_factory_provider()() as session:
            repo = TaskRepository(session)
            existing = await repo.list_by_conversation(conversation_id)
            sort_order = len(existing)
            task = await repo.save(
                Task(
                    id=new_uuid(),
                    conversation_id=conversation_id,
                    title=title,
                    content=content,
                    parent_id=parent_id or None,
                    priority=priority,
                    sort_order=sort_order,
                )
            )

        logger.debug("TaskTools - task_add | id=%s title=%s", task.id, title)
        return success_response({"id": task.id, "title": title, "task_status": task.status})

    async def task_update(
        self,
        id: str,
        title: str = "",
        content: str = "",
        status: str = "",
        priority: str = "",
    ) -> str:
        """更新单条任务，只更新传入的非空字段。"""
        if not id.strip():
            return error_response("id 不能为空", "EMPTY_TASK_ID")

        if self._conversation_id() is None:
            return self._context_error()

        async with self._session_factory_provider()() as session:
            repo = TaskRepository(session)
            existing = await repo.get(id)
            if existing is None:
                return error_response(f"任务不存在: {id}", "TASK_NOT_FOUND")

            updated = await repo.update(
                task_id=id,
                title=title if title else None,
                content=content if content else None,
                status=status if status else None,
                priority=priority if priority else None,
            )

        logger.debug("TaskTools - task_update | id=%s updated=%s", id, updated)
        return success_response({"id": id, "updated": updated})

    async def task_finish(self, id: str) -> str:
        """标记任务为已完成。"""
        if not id.strip():
            return error_response("id 不能为空", "EMPTY_TASK_ID")

        if self._conversation_id() is None:
            return self._context_error()

        async with self._session_factory_provider()() as session:
            repo = TaskRepository(session)
            existing = await repo.get(id)
            if existing is None:
                return error_response(f"任务不存在: {id}", "TASK_NOT_FOUND")

            await repo.update(task_id=id, status="completed")

        logger.debug("TaskTools - task_finish | id=%s", id)
        return success_response({"id": id, "task_status": "completed"})


__all__ = ["TaskTools"]

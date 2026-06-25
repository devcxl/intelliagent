"""任务管理工具 — task_write / task_add / task_update / task_finish。

通过 session_factory 创建 AsyncSession，使用 TaskRepository 进行持久化。
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Task
from src.db.repositories import TaskRepository
from src.db.repositories._utils import new_uuid
from src.utils.logger import logger

from .response import error_response, success_response

_task_ctx: ContextVar[tuple[async_sessionmaker[AsyncSession], str] | None] = ContextVar("task_ctx", default=None)


def set_task_context(
    session_factory: async_sessionmaker[AsyncSession] | None,
    conversation_id: str | None,
) -> None:
    """设置或清除任务工具的持久化上下文。

    Args:
        session_factory: async session factory，None 时清除
        conversation_id: 当前 Conversation ID，None 时清除
    """
    # ContextVar 让并发 Task 之间的 conversation 上下文互不污染。
    if session_factory is not None and conversation_id is not None:
        _task_ctx.set((session_factory, conversation_id))
    else:
        _task_ctx.set(None)


def _ensure_context() -> tuple[async_sessionmaker[AsyncSession], str]:
    ctx = _task_ctx.get()
    if ctx is None:
        raise RuntimeError("任务系统未初始化，缺少数据库或 Conversation 上下文")
    return ctx


async def task_write(tasks: str) -> str:
    """批量创建任务。替代旧版 todo_write，所有任务持久化到 SQLite。

    tasks 为 JSON 数组字符串，每项含 title(必填)/content/priority/parent_id 字段。
    自动补全 sort_order（按数组索引递增）。

    Args:
        tasks: JSON 数组字符串，每项为 {title, content?, priority?, parent_id?}

    Returns:
        JSON 格式的创建结果，包含 tasks 列表和 count
    """
    try:
        items = json.loads(tasks)
        if not isinstance(items, list):
            return error_response("tasks 必须是 JSON 数组", "INVALID_PARAMETERS")
    except json.JSONDecodeError as e:
        return error_response(f"tasks JSON 解析失败: {e}", "INVALID_PARAMETERS")

    try:
        factory, conv_id = _ensure_context()
    except RuntimeError as e:
        return error_response(str(e), "CONTEXT_NOT_INITIALIZED")

    async with factory() as session:
        repo = TaskRepository(session)

        existing = await repo.list_by_conversation(conv_id)
        base_order = len(existing)

        created: list[dict[str, Any]] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict) or "title" not in item:
                continue
            result = await repo.save(
                Task(
                    id=new_uuid(),
                    conversation_id=conv_id,
                    title=str(item["title"]),
                    content=str(item.get("content", "")),
                    parent_id=item.get("parent_id"),
                    priority=str(item.get("priority", "medium")),
                    sort_order=base_order + idx,
                )
            )
            created.append({"id": result["id"], "title": item["title"], "task_status": "pending"})

    logger.debug("TaskTools - task_write | count=%d", len(created))
    return success_response({"tasks": created, "count": len(created)})


async def task_add(
    title: str,
    content: str = "",
    priority: str = "medium",
    parent_id: str = "",
) -> str:
    """创建单条任务。

    Args:
        title: 任务标题
        content: 任务详细描述
        priority: 优先级（high/medium/low），默认 medium
        parent_id: 父任务 ID，空字符串表示顶级任务

    Returns:
        JSON 格式的创建结果，包含 id、title、task_status
    """
    title = title.strip()
    if not title:
        return error_response("title 不能为空", "EMPTY_TITLE")

    try:
        factory, conv_id = _ensure_context()
    except RuntimeError as e:
        return error_response(str(e), "CONTEXT_NOT_INITIALIZED")

    async with factory() as session:
        repo = TaskRepository(session)
        existing = await repo.list_by_conversation(conv_id)
        sort_order = len(existing)

        result = await repo.save(
            Task(
                id=new_uuid(),
                conversation_id=conv_id,
                title=title,
                content=content,
                parent_id=parent_id or None,
                priority=priority,
                sort_order=sort_order,
            )
        )

    logger.debug("TaskTools - task_add | id=%s title=%s", result["id"], title)
    return success_response({"id": result["id"], "title": title, "task_status": "pending"})


async def task_update(
    id: str,
    title: str = "",
    content: str = "",
    status: str = "",
    priority: str = "",
) -> str:
    """更新单条任务，只更新传入的非空字段。

    Args:
        id: 任务 ID（必填）
        title: 新标题，空字符串表示不更新
        content: 新内容，空字符串表示不更新
        status: 新状态（pending/in_progress/completed/cancelled），空字符串表示不更新
        priority: 新优先级，空字符串表示不更新

    Returns:
        JSON 格式的更新结果
    """
    if not id.strip():
        return error_response("id 不能为空", "EMPTY_TASK_ID")

    try:
        factory, _ = _ensure_context()
    except RuntimeError as e:
        return error_response(str(e), "CONTEXT_NOT_INITIALIZED")

    async with factory() as session:
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


async def task_finish(id: str) -> str:
    """标记任务为已完成。

    快捷方法，等价于 task_update(id=id, status="completed")。

    Args:
        id: 任务 ID

    Returns:
        JSON 格式的结果
    """
    if not id.strip():
        return error_response("id 不能为空", "EMPTY_TASK_ID")

    try:
        factory, _ = _ensure_context()
    except RuntimeError as e:
        return error_response(str(e), "CONTEXT_NOT_INITIALIZED")

    async with factory() as session:
        repo = TaskRepository(session)
        existing = await repo.get(id)
        if existing is None:
            return error_response(f"任务不存在: {id}", "TASK_NOT_FOUND")

        await repo.update(task_id=id, status="completed")

    logger.debug("TaskTools - task_finish | id=%s", id)
    return success_response({"id": id, "task_status": "completed"})

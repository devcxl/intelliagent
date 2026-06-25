"""Agent Team 内置工具 — 6 个异步 tool 函数 + 上下文注入。

上下文使用 ContextVar 存储 (async_sessionmaker, agent_id)。
每个 tool 调用从 factory 创建独立 AsyncSession。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.agent_team import (
    AgentNotFoundError,
    AgentTeamService,
    DuplicateNameError,
    EmptyContentError,
    InvalidStatusError,
)
from src.tools.response import error_response, success_response

logger = logging.getLogger(__name__)

_agent_team_ctx: ContextVar[tuple[async_sessionmaker[AsyncSession], str] | None] = ContextVar(
    "agent_team_ctx", default=None
)


def set_agent_team_context(session_factory: async_sessionmaker[AsyncSession] | None, agent_id: str | None) -> None:
    """设置或清除 Agent Team 上下文。

    Args:
        session_factory: async session factory，None 时清除
        agent_id: 当前 Agent ID，None 时清除
    """
    if session_factory is not None and agent_id is not None:
        _agent_team_ctx.set((session_factory, agent_id))
    else:
        _agent_team_ctx.set(None)


_CONTEXT_NOT_INITIALIZED_MSG = "Agent Team 上下文未初始化"


def _get_context() -> tuple[async_sessionmaker[AsyncSession], str]:
    ctx = _agent_team_ctx.get()
    if ctx is None:
        raise LookupError(_CONTEXT_NOT_INITIALIZED_MSG)
    return ctx


def _context_error() -> str:
    return error_response(_CONTEXT_NOT_INITIALIZED_MSG, "CONTEXT_NOT_INITIALIZED")


_EXCEPTION_MAP: dict[type[Exception], tuple[str, str]] = {
    AgentNotFoundError: ("Agent 不存在", "AGENT_NOT_FOUND"),
    EmptyContentError: ("消息内容不能为空", "EMPTY_CONTENT"),
    DuplicateNameError: ("Agent 名称已存在", "DUPLICATE_NAME"),
    InvalidStatusError: ("无效的状态值", "INVALID_STATUS"),
    ValueError: ("{}", "INVALID_PARAMETERS"),
}


_ServiceCall = Callable[..., Awaitable[str]]


async def _run_with_service(fn: _ServiceCall, *args: Any, **kwargs: Any) -> str:
    """统一 tool -> service 的样板流程，避免每个工具重复创建 session 和映射异常。"""

    try:
        factory, agent_id = _get_context()
    except LookupError:
        return _context_error()

    async with factory() as session:
        # 每次 tool 调用独立 session，避免跨工具调用共享事务状态。
        service = AgentTeamService(session)
        try:
            return await fn(service, agent_id, *args, **kwargs)
        except tuple(_EXCEPTION_MAP) as e:
            desc, code = _EXCEPTION_MAP[type(e)]
            return error_response(desc.format(str(e)), code)


async def send_message(to_agent_id: str, content: str) -> str:
    async def _send(service: AgentTeamService, current_agent_id: str, to_agent_id: str, content: str) -> str:
        result = await service.send_message(sender_id=current_agent_id, to_agent_id=to_agent_id, content=content)
        logger.debug("AgentTeam - send_message | from=%s to=%s msg_id=%s", current_agent_id, to_agent_id, result["id"])
        return success_response({"message_id": result["id"], "created_at": result["created_at"]})

    return await _run_with_service(_send, to_agent_id, content)


async def receive_message(limit: int = 20, offset: int = 0, unread_only: bool = False) -> str:
    async def _receive(service: AgentTeamService, current_agent_id: str) -> str:
        messages, total = await service.receive_message(
            receiver_id=current_agent_id, limit=limit, offset=offset, unread_only=unread_only
        )
        logger.debug(
            "AgentTeam - receive_message | receiver=%s count=%d total=%d unread_only=%s",
            current_agent_id,
            len(messages),
            total,
            unread_only,
        )
        return success_response({"messages": messages, "total": total})

    return await _run_with_service(_receive)


async def get_contacts(status: str | None = None) -> str:
    async def _contacts(service: AgentTeamService, current_agent_id: str) -> str:
        contacts = await service.get_contacts(current_agent_id=current_agent_id, status_filter=status)
        logger.debug("AgentTeam - get_contacts | agent=%s count=%d filter=%s", current_agent_id, len(contacts), status)
        return success_response({"contacts": contacts})

    return await _run_with_service(_contacts)


async def get_contact_detail(agent_id: str) -> str:
    async def _detail(service: AgentTeamService, current_agent_id: str) -> str:
        agent = await service.get_contact_detail(agent_id=agent_id)
        logger.debug("AgentTeam - get_contact_detail | current=%s target=%s", current_agent_id, agent_id)
        return success_response({"agent": agent})

    return await _run_with_service(_detail)


async def create_agent(
    name: str,
    desc: str = "",
    prompt: str = "",
    allowed_tools: str = "",
    model: str = "",
    workspace: str = "",
) -> str:
    async def _create(service: AgentTeamService, current_agent_id: str) -> str:
        agent = await service.create_agent(
            name=name,
            desc=desc,
            prompt=prompt,
            allowed_tools=allowed_tools,
            model=model,
            workspace=workspace,
        )
        logger.debug("AgentTeam - create_agent | current=%s name=%s id=%s", current_agent_id, name, agent["id"])
        return success_response({"agent": agent})

    return await _run_with_service(_create)


async def delete_agent(agent_id: str) -> str:
    async def _delete(service: AgentTeamService, current_agent_id: str) -> str:
        deleted = await service.delete_agent(agent_id=agent_id)
        logger.debug("AgentTeam - delete_agent | current=%s target=%s deleted=%s", current_agent_id, agent_id, deleted)
        return success_response({"deleted": deleted})

    return await _run_with_service(_delete)


__all__ = [
    "set_agent_team_context",
    "send_message",
    "receive_message",
    "get_contacts",
    "get_contact_detail",
    "create_agent",
    "delete_agent",
]

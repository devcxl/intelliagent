"""Agent Team 内置工具 — 6 个异步 tool 函数 + 上下文注入。

上下文注入对标 task_tools.set_task_context() 模式，但使用 ContextVar
保证 asyncio 安全性和并发隔离。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from src.core.agent_team import (
    AgentNotFoundError,
    AgentTeamService,
    DuplicateNameError,
    EmptyContentError,
    InvalidStatusError,
)
from src.db.agent_team_db import AgentTeamDB
from src.tools.response import error_response, success_response

logger = logging.getLogger(__name__)

# ── 上下文 ──────────────────────────────────────────────────────────────────
# ContextVar 存储 (db_path, agent_id)，None 表示未初始化
_agent_team_ctx: ContextVar[tuple[str, str] | None] = ContextVar(
    "agent_team_ctx", default=None
)


def set_agent_team_context(db_path: str | None, agent_id: str | None) -> None:
    """设置或清除 Agent Team 上下文。

    由 AgentRuntime.create_engine() 在创建 Engine 时调用。

    Args:
        db_path: SQLite 数据库文件路径，None 时清除上下文
        agent_id: 当前 Agent ID，None 时清除上下文
    """
    if db_path is not None and agent_id is not None:
        _agent_team_ctx.set((db_path, agent_id))
    else:
        _agent_team_ctx.set(None)


# ── 内部辅助 ────────────────────────────────────────────────────────────────


def _get_service() -> tuple[AgentTeamService, str]:
    """获取 Service 实例和当前 Agent ID。

    Returns:
        (AgentTeamService 实例, 当前 agent_id)

    Raises:
        LookupError: 上下文未初始化
    """
    ctx = _agent_team_ctx.get()
    if ctx is None:
        raise LookupError(_CONTEXT_NOT_INITIALIZED_MSG)
    db_path, agent_id = ctx
    db = AgentTeamDB(db_path)
    db.init_db()
    return AgentTeamService(db), agent_id


def _context_error() -> str:
    """返回上下文缺失的标准错误响应。"""
    return error_response(_CONTEXT_NOT_INITIALIZED_MSG, "CONTEXT_NOT_INITIALIZED")


_CONTEXT_NOT_INITIALIZED_MSG = "Agent Team 上下文未初始化"

# 异常 → (错误描述，错误码) 映射表
_EXCEPTION_MAP: dict[type[Exception], tuple[str, str]] = {
    AgentNotFoundError: ("Agent 不存在", "AGENT_NOT_FOUND"),
    EmptyContentError: ("消息内容不能为空", "EMPTY_CONTENT"),
    DuplicateNameError: ("Agent 名称已存在", "DUPLICATE_NAME"),
    InvalidStatusError: ("无效的状态值", "INVALID_STATUS"),
    ValueError: ("{}", "INVALID_PARAMETERS"),
}


# ── 6 个 Tool 函数 ─────────────────────────────────────────────────────────


async def send_message(to_agent_id: str, content: str) -> str:
    try:
        service, agent_id = _get_service()
    except LookupError:
        return _context_error()

    try:
        result = service.send_message(
            sender_id=agent_id, to_agent_id=to_agent_id, content=content
        )
        return success_response({
            "message_id": result["id"],
            "created_at": result["created_at"],
        })
    except (AgentNotFoundError, EmptyContentError) as e:
        desc, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc, code)
    finally:
        service.close()


async def receive_message(
    limit: int = 20, offset: int = 0, unread_only: bool = False
) -> str:
    try:
        service, agent_id = _get_service()
    except LookupError:
        return _context_error()

    try:
        messages, total = service.receive_message(
            receiver_id=agent_id, limit=limit, offset=offset, unread_only=unread_only
        )
        return success_response({"messages": messages, "total": total})
    finally:
        service.close()


async def get_contacts(status: str | None = None) -> str:
    try:
        service, agent_id = _get_service()
    except LookupError:
        return _context_error()

    try:
        contacts = service.get_contacts(
            current_agent_id=agent_id, status_filter=status
        )
        return success_response({"contacts": contacts})
    except InvalidStatusError as e:
        desc, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc, code)
    finally:
        service.close()


async def get_contact_detail(agent_id: str) -> str:
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        agent = service.get_contact_detail(agent_id=agent_id)
        return success_response({"agent": agent})
    except AgentNotFoundError as e:
        desc, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc, code)
    finally:
        service.close()


async def create_agent(name: str, desc: str = "", prompt: str = "") -> str:
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        agent = service.create_agent(name=name, desc=desc, prompt=prompt)
        return success_response({"agent": agent})
    except (DuplicateNameError, ValueError) as e:
        desc, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc.format(str(e)), code)
    finally:
        service.close()


async def delete_agent(agent_id: str) -> str:
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        deleted = service.delete_agent(agent_id=agent_id)
        return success_response({"deleted": deleted})
    except AgentNotFoundError as e:
        desc, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc, code)
    finally:
        service.close()


__all__ = [
    "set_agent_team_context",
    "send_message",
    "receive_message",
    "get_contacts",
    "get_contact_detail",
    "create_agent",
    "delete_agent",
]

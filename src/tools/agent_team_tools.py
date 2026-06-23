"""Agent Team 内置工具 — 6 个异步 tool 函数 + 上下文注入。

上下文注入对标 task_tools.set_task_context() 模式，但使用 ContextVar
保证 asyncio 安全性和并发隔离。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

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
        raise LookupError("Agent Team 上下文未初始化")
    db_path, agent_id = ctx
    db = AgentTeamDB(db_path)
    db.init_db()
    return AgentTeamService(db), agent_id


def _context_error() -> str:
    """返回上下文缺失的标准错误响应。"""
    return error_response("Agent Team 上下文未初始化", "CONTEXT_NOT_INITIALIZED")


# 异常 → (错误描述模板，错误码) 映射表
_EXCEPTION_MAP: dict[type[Exception], tuple[str, str]] = {
    AgentNotFoundError: ("Agent 不存在: {}", "AGENT_NOT_FOUND"),
    EmptyContentError: ("消息内容不能为空", "EMPTY_CONTENT"),
    DuplicateNameError: ("Agent 名称已存在: {}", "DUPLICATE_NAME"),
    InvalidStatusError: ("无效的状态值: {}", "INVALID_STATUS"),
}


# ── 6 个 Tool 函数 ─────────────────────────────────────────────────────────


async def send_message(to_agent_id: str, content: str) -> str:
    """向指定 Agent 发送消息。

    发送方身份由上下文注入，不可通过参数伪造。

    Args:
        to_agent_id: 目标 Agent ID（必填）
        content: 消息内容（必填）

    Returns:
        JSON: {"status":"ok","message_id":"<uuid>","created_at":"<iso8601>"}
        错误: {"status":"error","error":"...","code":"AGENT_NOT_FOUND|EMPTY_CONTENT|CONTEXT_NOT_INITIALIZED"}
    """
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
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)


async def receive_message(
    limit: int = 20, offset: int = 0, unread_only: bool = False
) -> str:
    """接收当前 Agent 的收件箱消息。

    返回的消息自动标记为已读。

    Args:
        limit: 返回条数上限（默认 20）
        offset: 偏移量（默认 0）
        unread_only: 仅返回未读消息（默认 False）

    Returns:
        JSON: {"status":"ok","messages":[...],"total":42}
        错误: {"status":"error","error":"...","code":"CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, agent_id = _get_service()
    except LookupError:
        return _context_error()

    messages, total = service.receive_message(
        receiver_id=agent_id, limit=limit, offset=offset, unread_only=unread_only
    )
    return success_response({"messages": messages, "total": total})


async def get_contacts(status: str | None = None) -> str:
    """查询通讯录，返回除当前 Agent 外的所有 Agent。

    Args:
        status: 按状态过滤（online / offline / busy），不传则返回全部

    Returns:
        JSON: {"status":"ok","contacts":[...]}
        错误: {"status":"error","error":"...","code":"CONTEXT_NOT_INITIALIZED|INVALID_STATUS"}
    """
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
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)


async def get_contact_detail(agent_id: str) -> str:
    """获取指定 Agent 的详细信息。

    Args:
        agent_id: 目标 Agent ID（必填）

    Returns:
        JSON: {"status":"ok","agent":{...}}
        错误: {"status":"error","error":"...","code":"AGENT_NOT_FOUND|CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        agent = service.get_contact_detail(agent_id=agent_id)
        return success_response({"agent": agent})
    except AgentNotFoundError as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)


async def create_agent(name: str, desc: str = "", prompt: str = "") -> str:
    """创建新 Agent。

    Agent ID 由系统自动生成（UUID），不在参数中暴露。

    Args:
        name: Agent 名称（必填，不可重名）
        desc: Agent 描述
        prompt: Agent 系统提示词

    Returns:
        JSON: {"status":"ok","agent":{...}}
        错误: {"status":"error","error":"...","code":"DUPLICATE_NAME|CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        agent = service.create_agent(name=name, desc=desc, prompt=prompt)
        return success_response({"agent": agent})
    except DuplicateNameError as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)


async def delete_agent(agent_id: str) -> str:
    """删除指定 Agent（软删除：status = 'deleted'）。

    消息历史保留，不级联删除。

    Args:
        agent_id: 目标 Agent ID（必填）

    Returns:
        JSON: {"status":"ok","deleted":true}
        错误: {"status":"error","error":"...","code":"AGENT_NOT_FOUND|CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        deleted = service.delete_agent(agent_id=agent_id)
        return success_response({"deleted": deleted})
    except AgentNotFoundError as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)


__all__ = [
    "set_agent_team_context",
    "send_message",
    "receive_message",
    "get_contacts",
    "get_contact_detail",
    "create_agent",
    "delete_agent",
]

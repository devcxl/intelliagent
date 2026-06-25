"""Agent Team 内置工具。

工具对象显式持有运行时依赖，避免通过 ContextVar/全局变量偷传 session 和 agent 身份。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.models import Agent, Relay
from src.db.repositories import RelayInboxItem
from src.services.agent_team import (
    AgentNotFoundError,
    AgentTeamService,
    DuplicateNameError,
    EmptyContentError,
    InvalidStatusError,
)
from src.tools.response import error_response, success_response

logger = logging.getLogger(__name__)

SessionFactoryProvider = Callable[[], async_sessionmaker[AsyncSession]]
_ServiceCall = Callable[..., Awaitable[str]]

_EXCEPTION_MAP: dict[type[Exception], tuple[str, str]] = {
    AgentNotFoundError: ("Agent 不存在", "AGENT_NOT_FOUND"),
    EmptyContentError: ("消息内容不能为空", "EMPTY_CONTENT"),
    DuplicateNameError: ("Agent 名称已存在", "DUPLICATE_NAME"),
    InvalidStatusError: ("无效的状态值", "INVALID_STATUS"),
    ValueError: ("{}", "INVALID_PARAMETERS"),
}


def _agent_to_dict(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "name": agent.name,
        "desc": agent.desc,
        "prompt": agent.prompt,
        "allowed_tools": agent.allowed_tools,
        "model": agent.model,
        "workspace": agent.workspace,
        "status": agent.status,
        "created_at": agent.created_at.isoformat() if agent.created_at else "",
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else "",
    }


def _relay_to_dict(relay: Relay, sender_name: str | None = None) -> dict[str, Any]:
    return {
        "id": relay.id,
        "sender_id": relay.sender_id,
        "receiver_id": relay.receiver_id,
        "content": relay.content,
        "is_read": 1 if relay.is_read else 0,
        "created_at": relay.created_at.isoformat() if relay.created_at else "",
        "sender_name": sender_name,
    }


class AgentTeamTools:
    """Agent Team 工具适配器，负责 service 调用和 JSON 响应格式化。"""

    def __init__(self, session_factory_provider: SessionFactoryProvider, agent_id: str) -> None:
        self._session_factory_provider = session_factory_provider
        self._agent_id = agent_id

    async def _run_with_service(self, fn: _ServiceCall, *args: Any, **kwargs: Any) -> str:
        async with self._session_factory_provider()() as session:
            # 每次 tool 调用独立 session，避免跨工具调用共享事务状态。
            service = AgentTeamService(session)
            try:
                return await fn(service, *args, **kwargs)
            except tuple(_EXCEPTION_MAP) as e:
                desc, code = _EXCEPTION_MAP[type(e)]
                return error_response(desc.format(str(e)), code)

    async def send_message(self, to_agent_id: str, content: str) -> str:
        async def _send(service: AgentTeamService, to_agent_id: str, content: str) -> str:
            message = await service.send_message(sender_id=self._agent_id, to_agent_id=to_agent_id, content=content)
            logger.debug("AgentTeam - send_message | from=%s to=%s msg_id=%s", self._agent_id, to_agent_id, message.id)
            return success_response(
                {"message_id": message.id, "created_at": message.created_at.isoformat() if message.created_at else ""}
            )

        return await self._run_with_service(_send, to_agent_id, content)

    async def receive_message(self, limit: int = 20, offset: int = 0, unread_only: bool = False) -> str:
        async def _receive(service: AgentTeamService) -> str:
            messages, total = await service.receive_message(
                receiver_id=self._agent_id, limit=limit, offset=offset, unread_only=unread_only
            )
            logger.debug(
                "AgentTeam - receive_message | receiver=%s count=%d total=%d unread_only=%s",
                self._agent_id,
                len(messages),
                total,
                unread_only,
            )
            return success_response({"messages": [_relay_item_to_dict(item) for item in messages], "total": total})

        return await self._run_with_service(_receive)

    async def get_contacts(self, status: str | None = None) -> str:
        async def _contacts(service: AgentTeamService) -> str:
            contacts = await service.get_contacts(current_agent_id=self._agent_id, status_filter=status)
            logger.debug(
                "AgentTeam - get_contacts | agent=%s count=%d filter=%s",
                self._agent_id,
                len(contacts),
                status,
            )
            return success_response({"contacts": [_agent_to_dict(agent) for agent in contacts]})

        return await self._run_with_service(_contacts)

    async def get_contact_detail(self, agent_id: str) -> str:
        async def _detail(service: AgentTeamService) -> str:
            agent = await service.get_contact_detail(agent_id=agent_id)
            logger.debug("AgentTeam - get_contact_detail | current=%s target=%s", self._agent_id, agent_id)
            return success_response({"agent": _agent_to_dict(agent)})

        return await self._run_with_service(_detail)

    async def create_agent(
        self,
        name: str,
        desc: str = "",
        prompt: str = "",
        allowed_tools: str = "",
        model: str = "",
        workspace: str = "",
    ) -> str:
        async def _create(service: AgentTeamService) -> str:
            agent = await service.create_agent(
                name=name,
                desc=desc,
                prompt=prompt,
                allowed_tools=allowed_tools,
                model=model,
                workspace=workspace,
            )
            logger.debug("AgentTeam - create_agent | current=%s name=%s id=%s", self._agent_id, name, agent.id)
            return success_response({"agent": _agent_to_dict(agent)})

        return await self._run_with_service(_create)

    async def delete_agent(self, agent_id: str) -> str:
        async def _delete(service: AgentTeamService) -> str:
            deleted = await service.delete_agent(agent_id=agent_id)
            logger.debug(
                "AgentTeam - delete_agent | current=%s target=%s deleted=%s",
                self._agent_id,
                agent_id,
                deleted,
            )
            return success_response({"deleted": deleted})

        return await self._run_with_service(_delete)


def _relay_item_to_dict(item: RelayInboxItem) -> dict[str, Any]:
    return _relay_to_dict(item.relay, sender_name=item.sender_name)


__all__ = ["AgentTeamTools"]

"""AgentTeamService — Agent 通讯录与消息中继业务逻辑。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Agent, Relay
from src.db.repositories import AgentRepository, RelayRepository
from src.db.repositories._utils import new_uuid


class AgentTeamError(Exception):
    """agent-team 业务异常基类。"""


class AgentNotFoundError(AgentTeamError):
    """Agent 不存在。"""

    code = "AGENT_NOT_FOUND"


class EmptyContentError(AgentTeamError):
    """消息内容为空。"""

    code = "EMPTY_CONTENT"


class DuplicateNameError(AgentTeamError):
    """同名 Agent 已存在。"""

    code = "DUPLICATE_NAME"


class InvalidStatusError(AgentTeamError):
    """状态值不合法。"""

    code = "INVALID_STATUS"


_CONTACT_STATUSES = frozenset({"online", "offline", "busy"})


class AgentTeamService:
    """封装 agent-team 业务逻辑：校验、ID 生成、错误码映射。

    该 service 依赖 Repository，因此放在 services 层，避免 core 层直接依赖 DB。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._agent_repo = AgentRepository(session)
        self._msg_repo = RelayRepository(session)

    async def send_message(self, sender_id: str, to_agent_id: str, content: str) -> dict:
        """发送消息给指定 Agent。"""
        if not content.strip():
            raise EmptyContentError()
        target = await self._agent_repo.get(to_agent_id)
        if target is None:
            raise AgentNotFoundError()

        msg_id = new_uuid()
        created_at = datetime.now(timezone.utc)
        await self._msg_repo.save(
            Relay(
                id=msg_id,
                sender_id=sender_id,
                receiver_id=to_agent_id,
                content=content.strip(),
                is_read=False,
                created_at=created_at,
            )
        )
        return {"id": msg_id, "created_at": created_at.isoformat()}

    async def receive_message(
        self,
        receiver_id: str,
        limit: int = 20,
        offset: int = 0,
        unread_only: bool = False,
    ) -> tuple[list[dict], int]:
        """收件箱查询，自动标记返回的消息为已读。"""
        receiver = await self._agent_repo.get(receiver_id)
        if receiver is None:
            raise AgentNotFoundError()
        messages, total = await self._msg_repo.list_by_receiver(receiver_id, limit, offset, unread_only)
        if messages:
            # 收件箱语义：成功返回给当前 Agent 的消息立即视为已读。
            await self._msg_repo.mark_as_read([m["id"] for m in messages])
        return (messages, total)

    async def get_contacts(
        self,
        current_agent_id: str,
        status_filter: str | None = None,
    ) -> list[dict]:
        """获取通讯录，排除已删除 Agent。"""
        if status_filter is not None and status_filter not in _CONTACT_STATUSES:
            raise InvalidStatusError()

        agents = await self._agent_repo.list(exclude_id=current_agent_id)
        agents = [a for a in agents if a["status"] != "deleted"]
        if status_filter is not None:
            agents = [a for a in agents if a["status"] == status_filter]
        return agents

    async def get_contact_detail(self, agent_id: str) -> dict:
        """查询 Agent 详情。"""
        agent = await self._agent_repo.get(agent_id)
        if agent is None:
            raise AgentNotFoundError()
        return agent

    async def create_agent(
        self,
        name: str,
        desc: str = "",
        prompt: str = "",
        allowed_tools: str = "",
        model: str = "",
        workspace: str = "",
    ) -> dict:
        """创建新 Agent，默认 status 为 offline。"""
        if not name.strip():
            raise ValueError("Agent name is required")
        existing = await self._agent_repo.get_by_name(name)
        if existing is not None:
            raise DuplicateNameError()

        now = datetime.now(timezone.utc)
        return await self._agent_repo.save(
            Agent(
                id=new_uuid(),
                name=name.strip(),
                desc=desc,
                prompt=prompt,
                status="offline",
                created_at=now,
                updated_at=now,
                allowed_tools=allowed_tools,
                model=model,
                workspace=workspace,
            )
        )

    async def delete_agent(self, agent_id: str) -> bool:
        """软删除 Agent（status -> 'deleted'）。"""
        agent = await self._agent_repo.get(agent_id)
        if agent is None:
            raise AgentNotFoundError()
        return await self._agent_repo.delete(agent_id)


__all__ = [
    "AgentNotFoundError",
    "AgentTeamError",
    "AgentTeamService",
    "DuplicateNameError",
    "EmptyContentError",
    "InvalidStatusError",
]

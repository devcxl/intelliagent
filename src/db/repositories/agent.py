"""AgentRepository — agents 表 CRUD。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Agent
from src.db.repositories._utils import now


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, agent: Agent) -> dict[str, Any]:
        self._session.add(agent)
        await self._session.commit()
        return await self._to_dict(agent)

    async def get(self, agent_id: str) -> dict[str, Any] | None:
        agent = await self._session.get(Agent, agent_id)
        if agent is None:
            return None
        return await self._to_dict(agent)

    async def get_by_name(self, name: str) -> dict[str, Any] | None:
        result = await self._session.execute(select(Agent).where(Agent.name == name))
        agent = result.scalar_one_or_none()
        if agent is None:
            return None
        return await self._to_dict(agent)

    async def list(
        self,
        exclude_id: str | None = None,
        status_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        stmt = select(Agent)
        if exclude_id is not None:
            stmt = stmt.where(Agent.id != exclude_id)
        if status_filter is not None:
            stmt = stmt.where(Agent.status == status_filter)
        stmt = stmt.order_by(Agent.name.asc())
        result = await self._session.execute(stmt)
        return [await self._to_dict(a) for a in result.scalars()]

    async def delete(self, agent_id: str) -> bool:
        agent = await self._session.get(Agent, agent_id)
        if agent is None:
            return False
        agent.status = "deleted"
        agent.updated_at = now()
        await self._session.commit()
        return True

    async def _to_dict(self, agent: Agent) -> dict[str, Any]:
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

"""AgentRepository — agents 表 CRUD。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Agent
from src.db.repositories._utils import now


class AgentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, agent: Agent) -> Agent:
        self._session.add(agent)
        await self._session.commit()
        return agent

    async def get(self, agent_id: str) -> Agent | None:
        return await self._session.get(Agent, agent_id)

    async def get_by_name(self, name: str) -> Agent | None:
        result = await self._session.execute(select(Agent).where(Agent.name == name))
        return result.scalar_one_or_none()

    async def list(
        self,
        exclude_id: str | None = None,
        status_filter: str | None = None,
    ) -> list[Agent]:
        stmt = select(Agent)
        if exclude_id is not None:
            stmt = stmt.where(Agent.id != exclude_id)
        if status_filter is not None:
            stmt = stmt.where(Agent.status == status_filter)
        stmt = stmt.order_by(Agent.name.asc())
        result = await self._session.execute(stmt)
        return list(result.scalars())

    async def delete(self, agent_id: str) -> bool:
        agent = await self._session.get(Agent, agent_id)
        if agent is None:
            return False
        agent.status = "deleted"
        agent.updated_at = now()
        await self._session.commit()
        return True

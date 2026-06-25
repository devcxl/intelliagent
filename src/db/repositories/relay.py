"""RelayRepository — relays 表 CRUD，Agent 间消息中继。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Agent, Relay


@dataclass(frozen=True)
class RelayInboxItem:
    """收件箱查询投影：消息实体 + 发送方展示名。"""

    relay: Relay
    sender_name: str | None


class RelayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, relay: Relay) -> Relay:
        self._session.add(relay)
        await self._session.commit()
        return relay

    async def list_by_receiver(
        self,
        receiver_id: str,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> tuple[list[RelayInboxItem], int]:
        stmt = select(Relay).where(Relay.receiver_id == receiver_id)
        if unread_only:
            stmt = stmt.where(Relay.is_read == False)  # noqa: E712
        stmt = stmt.order_by(Relay.created_at.desc())

        count_stmt = select(func.count()).select_from(Relay).where(Relay.receiver_id == receiver_id)
        if unread_only:
            count_stmt = count_stmt.where(Relay.is_read == False)  # noqa: E712
        count_result = await self._session.execute(count_stmt)
        total = count_result.scalar_one()

        paged_stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(paged_stmt)
        messages = list(result.scalars().all())

        sender_names = await self._load_sender_names(messages)
        items = [RelayInboxItem(relay=message, sender_name=sender_names.get(message.sender_id)) for message in messages]

        return items, total

    async def _load_sender_names(self, messages: list[Relay]) -> dict[str, str]:
        sender_ids = {message.sender_id for message in messages}
        if not sender_ids:
            return {}

        result = await self._session.execute(select(Agent.id, Agent.name).where(Agent.id.in_(sender_ids)))
        return {agent_id: name for agent_id, name in result.all()}

    async def mark_as_read(self, message_ids: list[str]) -> None:
        if not message_ids:
            return
        stmt = update(Relay).where(Relay.id.in_(message_ids)).values(is_read=True)
        await self._session.execute(stmt)
        await self._session.commit()

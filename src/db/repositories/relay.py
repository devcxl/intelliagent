"""RelayRepository — relays 表 CRUD，Agent 间消息中继。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import Agent, Relay


class RelayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, relay: Relay) -> dict[str, Any]:
        self._session.add(relay)
        await self._session.commit()
        return {
            "id": relay.id,
            "sender_id": relay.sender_id,
            "receiver_id": relay.receiver_id,
            "content": relay.content,
            "is_read": 1 if relay.is_read else 0,
            "created_at": relay.created_at.isoformat() if relay.created_at else "",
        }

    async def list_by_receiver(
        self,
        receiver_id: str,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        stmt = select(Relay).where(Relay.receiver_id == receiver_id)
        if unread_only:
            stmt = stmt.where(Relay.is_read == False)  # noqa: E712
        stmt = stmt.order_by(Relay.created_at.desc())

        count_stmt = select(Relay).where(Relay.receiver_id == receiver_id)
        if unread_only:
            count_stmt = count_stmt.where(Relay.is_read == False)  # noqa: E712
        count_result = await self._session.execute(count_stmt)
        total = len(count_result.scalars().all())

        paged_stmt = stmt.offset(offset).limit(limit)
        result = await self._session.execute(paged_stmt)
        messages = result.scalars().all()

        items = []
        for m in messages:
            d = {
                "id": m.id,
                "sender_id": m.sender_id,
                "receiver_id": m.receiver_id,
                "content": m.content,
                "is_read": 1 if m.is_read else 0,
                "created_at": m.created_at.isoformat() if m.created_at else "",
                "sender_name": None,
            }
            sender = await self._session.get(Agent, m.sender_id)
            if sender is not None:
                d["sender_name"] = sender.name
            items.append(d)

        return items, total

    async def mark_as_read(self, message_ids: list[str]) -> None:
        if not message_ids:
            return
        stmt = update(Relay).where(Relay.id.in_(message_ids)).values(is_read=True)
        await self._session.execute(stmt)
        await self._session.commit()

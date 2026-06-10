#!/usr/bin/env python3
"""ExecutionTrace repository。"""

from __future__ import annotations

import json

from sqlalchemy import select

from src.db.models import ExecutionTrace
from src.db.session import DatabaseSessionManager


class ExecutionTraceRepository:
    def __init__(self, session_manager: DatabaseSessionManager):
        self.session_manager = session_manager

    async def create(
        self,
        *,
        trace_id: str,
        run_id: str,
        iteration: int,
        trace_type: str,
        data: dict,
    ) -> ExecutionTrace:
        async with self.session_manager.session() as session:
            trace = ExecutionTrace(
                id=trace_id,
                run_id=run_id,
                iteration=iteration,
                type=trace_type,
                data=json.dumps(data, ensure_ascii=False),
            )
            session.add(trace)
            await session.commit()
            await session.refresh(trace)
            return trace

    async def list_by_run(self, run_id: str) -> list[ExecutionTrace]:
        async with self.session_manager.session() as session:
            result = await session.execute(
                select(ExecutionTrace)
                .where(ExecutionTrace.run_id == run_id)
                .order_by(ExecutionTrace.iteration.asc(), ExecutionTrace.created_at.asc())
            )
            return list(result.scalars().all())

#!/usr/bin/env python3
"""Run repository。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models import Run
from src.db.session import DatabaseSessionManager, utcnow


ACTIVE_RUN_STATUSES = {"pending", "running"}


class RunRepository:
    def __init__(self, session_manager: DatabaseSessionManager):
        self.session_manager = session_manager

    async def create(
        self,
        *,
        run_id: str,
        conversation_id: str,
        task_snapshot: str,
        status: str = "pending",
        max_iterations: int = 10,
        current_iteration: int = 0,
        error: str | None = None,
        cancel_requested: bool = False,
        source_run_id: str | None = None,
        ) -> Run:
        async with self.session_manager.session() as session:
            run = Run(
                id=run_id,
                conversation_id=conversation_id,
                task_snapshot=task_snapshot,
                status=status,
                max_iterations=max_iterations,
                current_iteration=current_iteration,
                error=error,
                cancel_requested=cancel_requested,
                source_run_id=source_run_id,
            )
            try:
                session.add(run)
                await session.commit()
                await session.refresh(run)
                return run
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError(
                    f"Conversation {conversation_id} 已存在活跃 run"
                ) from exc

    async def get(self, run_id: str) -> Run | None:
        async with self.session_manager.session() as session:
            return await session.get(Run, run_id)

    async def get_active_by_conversation(self, conversation_id: str) -> Run | None:
        async with self.session_manager.session() as session:
            result = await session.execute(
                select(Run)
                .where(Run.conversation_id == conversation_id)
                .where(Run.status.in_(ACTIVE_RUN_STATUSES))
                .order_by(Run.created_at.desc())
            )
            return result.scalars().first()

    async def list_by_conversation(self, conversation_id: str) -> list[Run]:
        async with self.session_manager.session() as session:
            result = await session.execute(
                select(Run)
                .where(Run.conversation_id == conversation_id)
                .order_by(Run.created_at.asc())
            )
            return list(result.scalars().all())

    async def update_status(
        self,
        run_id: str,
        *,
        status: str | None = None,
        current_iteration: int | None = None,
        error: str | None = None,
        cancel_requested: bool | None = None,
    ) -> Run | None:
        async with self.session_manager.session() as session:
            run = await session.get(Run, run_id)
            if run is None:
                return None

            if status is not None:
                run.status = status
            if current_iteration is not None:
                run.current_iteration = current_iteration
            if cancel_requested is not None:
                run.cancel_requested = cancel_requested

            run.error = error
            run.updated_at = utcnow()

            try:
                await session.commit()
                await session.refresh(run)
                return run
            except IntegrityError as exc:
                await session.rollback()
                raise ValueError(
                    f"Conversation {run.conversation_id} 已存在活跃 run"
                ) from exc

    async def delete(self, run_id: str) -> bool:
        async with self.session_manager.session() as session:
            run = await session.get(Run, run_id)
            if run is None:
                return False

            await session.delete(run)
            await session.commit()
            return True

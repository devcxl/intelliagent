"""StorageStore：SQLite 承载的 append-only entry 存储（ADR 0010 复刻 pi 的 append-only 树语义）。

entry 以 parent_id 形成链/树；compaction、Run 状态更新同样以追加 entry 表达，
上下文视图（Projection）与 Run 状态都是读取时现算的投影，原始记录永不删除。
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.plugins.storage.errors import EntryNotFoundError, StorageError
from src.plugins.storage.models import APPEND_ONLY_TRIGGER_STATEMENTS, Base, EntryRow
from src.plugins.storage.records import (
    ENTRY_TYPE_COMPACTION,
    ENTRY_TYPE_MESSAGE,
    ENTRY_TYPE_RUN,
    ENTRY_TYPE_RUN_STATUS,
    CompactionRecord,
    Entry,
    MessagePayload,
    Projection,
    RunRecord,
)


def _to_async_sqlite_url(database_url: str) -> str:
    """把文件路径 / :memory: / sqlite URL 统一为 aiosqlite 异步 URL。"""
    if database_url == ":memory:":
        return "sqlite+aiosqlite:///:memory:"
    if database_url.startswith("sqlite+aiosqlite://"):
        return database_url
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    if "://" in database_url:
        raise StorageError(f"only SQLite storage is supported, got: {database_url}")
    return f"sqlite+aiosqlite:///{database_url}"


def _to_entry(row: EntryRow) -> Entry:
    return Entry(
        id=row.id, parent_id=row.parent_id, type=row.type, payload=dict(row.payload), created_at=row.created_at
    )


def _project_run(run_row: EntryRow, status_rows: Sequence[EntryRow]) -> RunRecord:
    """把 run entry 与依次追加的 run_status entry 投影为 Run 当前状态。"""
    payload = run_row.payload
    status = payload.get("status", "")
    token_usage: dict[str, int] | None = None
    updated_at = run_row.created_at
    for row in status_rows:
        status = row.payload.get("status", status)
        if row.payload.get("token_usage") is not None:
            token_usage = dict(row.payload["token_usage"])
        updated_at = row.created_at
    return RunRecord(
        run_id=run_row.id,
        status=status,
        model=payload.get("model"),
        token_usage=token_usage,
        created_at=run_row.created_at,
        updated_at=updated_at,
    )


class StorageStore:
    """append-only 的 entry 存储：一切记录以追加 entry 表达，无 UPDATE/DELETE 路径。

    SQLite 是单写者，存储层用一把 asyncio 锁把进程内操作串行化；engine 固定 StaticPool
    单连接，让 :memory: 与文件库行为一致，也避免共享连接上的事务交错。
    """

    def __init__(self, database_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(_to_async_sqlite_url(database_url), poolclass=StaticPool)
        self._sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """建表并挂上 append-only 触发器；幂等，各写入方法也会惰性调用。"""
        async with self._lock:
            await self._initialize()

    async def close(self) -> None:
        """释放底层连接。"""
        await self._engine.dispose()

    async def append_entry(
        self,
        entry_type: str,
        payload: Mapping[str, Any],
        *,
        parent_id: str | None = None,
        entry_id: str | None = None,
    ) -> Entry:
        """追加一条 entry；parent_id 指向已有 entry 时形成链/树。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                row = await self._insert_entry(session, entry_type, payload, parent_id=parent_id, entry_id=entry_id)
                return _to_entry(row)

    async def get_entry(self, entry_id: str) -> Entry | None:
        """按 id 取单条 entry；不存在返回 None。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                row = await session.get(EntryRow, entry_id)
                return _to_entry(row) if row is not None else None

    async def append_message(self, payload: MessagePayload, *, parent_id: str | None = None) -> Entry:
        """追加 message entry：Conversation/Message 经 entry 抽象落库。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                row = await self._insert_entry(
                    session, ENTRY_TYPE_MESSAGE, payload.model_dump(exclude_none=True), parent_id=parent_id
                )
                return _to_entry(row)

    async def append_compaction(
        self,
        *,
        summary: str,
        first_kept_entry_id: str,
        prompt_checkpoint: Mapping[str, Any],
        parent_id: str | None = None,
    ) -> CompactionRecord:
        """追加 compaction 记录：摘要 + 保留切点 + prompt checkpoint，原始记录不删。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                if await session.get(EntryRow, first_kept_entry_id) is None:
                    raise EntryNotFoundError(f"first_kept_entry_id '{first_kept_entry_id}' does not exist")
                row = await self._insert_entry(
                    session,
                    ENTRY_TYPE_COMPACTION,
                    {
                        "summary": summary,
                        "first_kept_entry_id": first_kept_entry_id,
                        "prompt_checkpoint": dict(prompt_checkpoint),
                    },
                    parent_id=parent_id,
                )
                return CompactionRecord.from_entry(_to_entry(row))

    async def append_run(self, *, status: str = "running", model: str | None = None) -> RunRecord:
        """创建一次 Engine 执行的 Run 记录；run entry 的 id 即 run_id。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                row = await self._insert_entry(session, ENTRY_TYPE_RUN, {"status": status, "model": model})
                return _project_run(row, [])

    async def append_run_status(
        self,
        run_id: str,
        *,
        status: str,
        token_usage: Mapping[str, int] | None = None,
    ) -> RunRecord:
        """以追加 run_status entry 表达 Run 状态更新（纯 append-only，不改写 run entry）。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                run_row = await self._require_run_row(session, run_id)
                status_rows = await self._run_status_rows(session, run_row)
                payload: dict[str, Any] = {"status": status}
                if token_usage is not None:
                    payload["token_usage"] = dict(token_usage)
                tip_id = status_rows[-1].id if status_rows else run_row.id
                new_row = await self._insert_entry(session, ENTRY_TYPE_RUN_STATUS, payload, parent_id=tip_id)
                return _project_run(run_row, [*status_rows, new_row])

    async def get_run(self, run_id: str) -> RunRecord | None:
        """投影出 Run 当前状态；run_id 不存在返回 None。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                run_row = await session.get(EntryRow, run_id)
                if run_row is None:
                    return None
                self._require_run_type(run_row)
                status_rows = await self._run_status_rows(session, run_row)
                return _project_run(run_row, status_rows)

    async def run_entries(self, run_id: str) -> tuple[Entry, ...]:
        """run 的完整 entry 链：run entry + 依次追加的 run_status entry。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                run_row = await self._require_run_row(session, run_id)
                status_rows = await self._run_status_rows(session, run_row)
                return tuple(_to_entry(row) for row in [run_row, *status_rows])

    async def branch_path(self, entry_id: str) -> tuple[Entry, ...]:
        """按 parent 链取分支路径：root → entry_id（含两端）。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                rows = await self._branch_rows(session, entry_id)
                return tuple(_to_entry(row) for row in rows)

    async def projection(self, leaf_entry_id: str) -> Projection:
        """现算投影（CONTEXT 术语：Projection）：compaction 摘要 + 保留段 entry 序列。

        取分支路径上最新的 compaction 记录；保留段为 first_kept_entry_id 起到 leaf 的 entry。
        compaction entry 本身由摘要代表、不进序列，更早的 compaction 记录同样不进投影但保留在库中。
        """
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                rows = await self._branch_rows(session, leaf_entry_id)
        path = [_to_entry(row) for row in rows]
        compactions = [entry for entry in path if entry.type == ENTRY_TYPE_COMPACTION]
        if not compactions:
            return Projection(compaction=None, entries=tuple(path))
        latest = CompactionRecord.from_entry(compactions[-1])
        ids = [entry.id for entry in path]
        if latest.first_kept_entry_id not in ids:
            raise StorageError(
                f"compaction '{latest.entry_id}' first_kept_entry_id '{latest.first_kept_entry_id}' "
                f"is not on the branch path of '{leaf_entry_id}'"
            )
        kept = path[ids.index(latest.first_kept_entry_id) :]
        kept_entries = tuple(entry for entry in kept if entry.type != ENTRY_TYPE_COMPACTION)
        return Projection(compaction=latest, entries=kept_entries)

    async def _initialize(self) -> None:
        if self._initialized:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for statement in APPEND_ONLY_TRIGGER_STATEMENTS:
                await conn.exec_driver_sql(statement)
        self._initialized = True

    async def _insert_entry(
        self,
        session: AsyncSession,
        entry_type: str,
        payload: Mapping[str, Any],
        *,
        parent_id: str | None = None,
        entry_id: str | None = None,
    ) -> EntryRow:
        if not entry_type:
            raise StorageError("entry type must not be empty")
        if parent_id is not None:
            if await session.get(EntryRow, parent_id) is None:
                raise EntryNotFoundError(f"parent entry '{parent_id}' does not exist")
        row = EntryRow(id=entry_id or uuid4().hex, parent_id=parent_id, type=entry_type, payload=dict(payload))
        session.add(row)
        await session.flush()
        # 回读 DB 归一化后的值，保证与后续读取完全一致（created_at/payload round-trip）
        await session.refresh(row)
        await session.commit()
        return row

    async def _branch_rows(self, session: AsyncSession, entry_id: str) -> list[EntryRow]:
        rows: list[EntryRow] = []
        seen: set[str] = set()
        current_id: str | None = entry_id
        while current_id is not None:
            if current_id in seen:
                raise StorageError(f"entry chain contains a cycle at '{current_id}'")
            seen.add(current_id)
            row = await session.get(EntryRow, current_id)
            if row is None:
                raise EntryNotFoundError(f"entry '{current_id}' does not exist")
            rows.append(row)
            current_id = row.parent_id
        rows.reverse()
        return rows

    async def _require_run_row(self, session: AsyncSession, run_id: str) -> EntryRow:
        row = await session.get(EntryRow, run_id)
        if row is None:
            raise EntryNotFoundError(f"run entry '{run_id}' does not exist")
        self._require_run_type(row)
        return row

    @staticmethod
    def _require_run_type(row: EntryRow) -> None:
        if row.type != ENTRY_TYPE_RUN:
            raise StorageError(f"entry '{row.id}' is not a run entry (type '{row.type}')")

    async def _run_status_rows(self, session: AsyncSession, run_row: EntryRow) -> list[EntryRow]:
        """沿 parent 链取 run 下依次追加的 run_status entry。"""
        rows: list[EntryRow] = []
        current = run_row
        while True:
            child = (
                (
                    await session.execute(
                        select(EntryRow).where(EntryRow.parent_id == current.id, EntryRow.type == ENTRY_TYPE_RUN_STATUS)
                    )
                )
                .scalars()
                .first()
            )
            if child is None:
                return rows
            rows.append(child)
            current = child

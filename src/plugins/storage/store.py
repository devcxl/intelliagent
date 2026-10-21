"""StorageStore：SQLite 承载的 append-only entry 存储（ADR 0010 复刻 pi 的 append-only 树语义）。

entry 以 parent_id 形成链/树；compaction、Run 状态更新同样以追加 entry 表达，
上下文视图（Projection）与 Run 状态都是读取时现算的投影，原始记录永不删除。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.plugins.storage.errors import EntryNotFoundError, StorageError
from src.plugins.storage.messages import entry_message, message_entries, message_payload
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


def _json_safe_checkpoint(checkpoint: Mapping[str, Any]) -> dict[str, Any]:
    """校验 prompt_checkpoint 可被 JSON 无损往返（键须为字符串），否则报 StorageError。

    JSON 序列化会把 int 键静默转字符串、对不可序列化值抛裸 TypeError——两者都破坏
    "prompt checkpoint 保真"（US37），必须在写入前显式拒绝。
    """
    result: dict[str, Any] = {}
    for key, value in checkpoint.items():
        if not isinstance(key, str):
            raise StorageError(f"prompt_checkpoint keys must be strings, got {type(key).__name__}: {key!r}")
        try:
            json.dumps(value)
        except (TypeError, ValueError) as exc:
            raise StorageError(f"prompt_checkpoint['{key}'] is not JSON-serializable: {exc}") from exc
        result[key] = value
    return result


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

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """串行化入口：进程内锁 → 惰性初始化 → 借出 session（九个公开方法共享的骨架）。"""
        async with self._lock:
            await self._initialize()
            async with self._sessions() as session:
                yield session

    async def append_entry(
        self,
        entry_type: str,
        payload: Mapping[str, Any],
        *,
        parent_id: str | None = None,
        entry_id: str | None = None,
    ) -> Entry:
        """追加一条 entry；parent_id 指向已有 entry 时形成链/树。"""
        async with self._session() as session:
            row = await self._insert_entry(session, entry_type, payload, parent_id=parent_id, entry_id=entry_id)
            return _to_entry(row)

    async def get_entry(self, entry_id: str) -> Entry | None:
        """按 id 取单条 entry；不存在返回 None。"""
        async with self._session() as session:
            row = await session.get(EntryRow, entry_id)
            return _to_entry(row) if row is not None else None

    async def append_message(self, payload: MessagePayload, *, parent_id: str | None = None) -> Entry:
        """追加 message entry：Conversation/Message 经 entry 抽象落库。"""
        async with self._session() as session:
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
        """追加 compaction 记录：摘要 + 保留切点 + prompt checkpoint，原始记录不删。

        切点必须在 parent 的分支路径上——写入时前置校验（append-only 无法事后修复坏记录）。
        """
        checkpoint = _json_safe_checkpoint(prompt_checkpoint)
        async with self._session() as session:
            if parent_id is None:
                raise StorageError("append_compaction requires parent_id (the branch leaf)")
            path = await self._branch_rows(session, parent_id)
            path_ids = {row.id for row in path}
            if first_kept_entry_id not in path_ids:
                raise StorageError(
                    f"first_kept_entry_id '{first_kept_entry_id}' is not on the branch path of '{parent_id}'"
                )
            row = await self._insert_entry(
                session,
                ENTRY_TYPE_COMPACTION,
                {
                    "summary": summary,
                    "first_kept_entry_id": first_kept_entry_id,
                    "prompt_checkpoint": checkpoint,
                },
                parent_id=parent_id,
            )
            return CompactionRecord.from_entry(_to_entry(row))

    async def append_run(
        self, *, status: str = "running", model: str | None = None, parent_id: str | None = None
    ) -> RunRecord:
        """创建一次 Engine 执行的 Run 记录；run entry 的 id 即 run_id。

        parent_id 指向会话分支的 leaf entry，把 Run 关联到会话（US38 可观测性）。
        """
        async with self._session() as session:
            row = await self._insert_entry(
                session, ENTRY_TYPE_RUN, {"status": status, "model": model}, parent_id=parent_id
            )
            return _project_run(row, [])

    async def append_run_status(
        self,
        run_id: str,
        *,
        status: str,
        token_usage: Mapping[str, int] | None = None,
    ) -> RunRecord:
        """以追加 run_status entry 表达 Run 状态更新（纯 append-only，不改写 run entry）。"""
        async with self._session() as session:
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
        async with self._session() as session:
            run_row = await session.get(EntryRow, run_id)
            if run_row is None:
                return None
            self._require_run_type(run_row)
            status_rows = await self._run_status_rows(session, run_row)
            return _project_run(run_row, status_rows)

    async def run_entries(self, run_id: str) -> tuple[Entry, ...]:
        """run 的完整 entry 链：run entry + 依次追加的 run_status entry。"""
        async with self._session() as session:
            run_row = await self._require_run_row(session, run_id)
            status_rows = await self._run_status_rows(session, run_row)
            return tuple(_to_entry(row) for row in [run_row, *status_rows])

    async def append_chat_message(self, message: dict[str, Any], *, parent_id: str | None = None) -> str:
        """追加一条 chat 消息 entry，返回 entry id（ChatMessage 映射在 storage 侧内部完成）。"""
        entry = await self.append_message(message_payload(message), parent_id=parent_id)
        return entry.id

    async def chat_projection(self, leaf_entry_id: str) -> tuple[str | None, list[tuple[str, dict[str, Any]]]]:
        """现算投影的高层视图：(摘要 | None, [(entry_id, ChatMessage), ...])。

        compaction 记录的摘要 + 保留段 message entry 重建的消息序列；entry_id 供切点定位。
        """
        projection = await self.projection(leaf_entry_id)
        kept = [(entry.id, entry_message(entry)) for entry in message_entries(list(projection.entries))]
        summary = projection.compaction.summary if projection.compaction is not None else None
        return summary, kept

    async def latest_leaf(self) -> str | None:
        """取最新追加的 entry id（重启续接的 leaf 锚点）；空库返回 None。

        append-only 单写者下最新 entry 即活跃分支的 leaf。
        """
        async with self._session() as session:
            row = (await session.execute(select(EntryRow).order_by(EntryRow.created_at.desc()))).scalars().first()
            return row.id if row is not None else None

    async def branch_path(self, entry_id: str) -> tuple[Entry, ...]:
        """按 parent 链取分支路径：root → entry_id（含两端）。"""
        async with self._session() as session:
            rows = await self._branch_rows(session, entry_id)
            return tuple(_to_entry(row) for row in rows)

    async def projection(self, leaf_entry_id: str) -> Projection:
        """现算投影（CONTEXT 术语：Projection）：compaction 摘要 + 保留段 entry 序列。

        取分支路径上最新的 compaction 记录；保留段为 first_kept_entry_id 起到 leaf 的 entry。
        compaction entry 本身由摘要代表、不进序列，更早的 compaction 记录同样不进投影但保留在库中。
        """
        async with self._session() as session:
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
        """沿 parent 链取 run 下依次追加的 run_status entry。

        同一 parent 挂多个 run_status 子节点即状态链分叉（跨进程竞争等），
        投影语义要求唯一后继，显式报错而非静默取其一（append-only 无法事后修复）。
        """
        rows: list[EntryRow] = []
        seen: set[str] = set()
        current = run_row
        while True:
            if current.id in seen:
                raise StorageError(f"run status chain contains a cycle at '{current.id}'")
            seen.add(current.id)
            children = (
                (
                    await session.execute(
                        select(EntryRow).where(EntryRow.parent_id == current.id, EntryRow.type == ENTRY_TYPE_RUN_STATUS)
                    )
                )
                .scalars()
                .all()
            )
            if not children:
                return rows
            if len(children) > 1:
                raise StorageError(
                    f"run status chain forked at '{current.id}': {len(children)} run_status children "
                    f"(ids: {[child.id for child in children]})"
                )
            rows.append(children[0])
            current = children[0]

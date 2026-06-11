#!/usr/bin/env python3
"""PR4 run 生命周期集成测试。"""

from unittest.mock import Mock

from src.db.manager import DatabaseManager
from src.services import RunService


class FakeSuccessfulEngine:
    def __init__(self):
        self.last_task = None
        self.last_max_iterations = None

    async def run_async(self, task, max_iterations=10, **kwargs):
        self.last_task = task
        self.last_max_iterations = max_iterations
        return {"success": True, "answer": "done", "num_turns": 2}


async def test_run_service_persists_run_messages_and_traces(tmp_path):
    db_path = str(tmp_path / "lifecycle" / "intelliagent.db")
    db = DatabaseManager(db_path)
    await db.initialize()
    await db.create_session(session_id="conversation-1", title="测试会话", task="测试任务")

    runtime = Mock()
    runtime.create_engine.return_value = FakeSuccessfulEngine()
    service = RunService(runtime, db_manager=db)

    result = await service.run_task_async(
        task="测试任务", max_iterations=3, conversation_id="conversation-1",
    )

    assert result["success"] is True
    run = await db.get_run(result["run_id"])
    assert run is not None
    assert run["status"] == "completed"
    assert run["current_iteration"] == 2

    messages = await db.get_messages("conversation-1")
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"


async def test_run_service_cancel_run_sets_cancel_requested_flag(tmp_path):
    db_path = str(tmp_path / "cancel" / "intelliagent.db")
    db = DatabaseManager(db_path)
    await db.initialize()
    await db.create_session(session_id="conversation-4", title="取消会话")

    runtime = Mock()
    service = RunService(runtime, db_manager=db)

    await db.create_run(
        run_id="run-pending", conversation_id="conversation-4",
        task_snapshot="取消任务", status="running", max_iterations=3,
    )

    cancelled = await service.cancel_run("run-pending")
    assert cancelled is True

    updated = await db.get_run("run-pending")
    assert updated is not None
    assert updated["cancel_requested"] is True


async def test_rerun_rejects_cross_conversation_source_run(tmp_path):
    db_path = str(tmp_path / "lineage" / "intelliagent.db")
    db = DatabaseManager(db_path)
    await db.initialize()
    await db.create_session(session_id="conversation-a", title="A", task="任务 A")
    await db.create_session(session_id="conversation-b", title="B", task="任务 B")

    runtime = Mock()
    runtime.create_engine.return_value = FakeSuccessfulEngine()
    service = RunService(runtime, db_manager=db)

    source_run = await db.create_run(
        run_id="run-a-1", conversation_id="conversation-a",
        task_snapshot="任务 A", status="completed", max_iterations=3,
    )

    try:
        await service.rerun(
            conversation_id="conversation-b", task="任务 B",
            max_iterations=3, source_run_id=source_run["id"],
        )
    except ValueError as exc:
        assert "不属于当前会话" in str(exc)
    else:
        raise AssertionError("应拒绝跨会话使用 source_run_id")

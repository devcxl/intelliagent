#!/usr/bin/env python3
"""PR4 run 生命周期集成测试。"""

from unittest.mock import Mock

from src.db.manager import DatabaseManager
from src.runtime import RunService


class FakeSuccessfulEngine:
    def __init__(self):
        self.last_task = None
        self.last_max_iterations = None

    async def run(self, task, max_iterations=None, history_context=None):
        self.last_task = task
        self.last_max_iterations = max_iterations
        self.last_history_context = history_context
        return {"success": True, "answer": "done", "num_turns": 2}


async def test_run_service_persists_run_and_messages(tmp_path):
    db_path = str(tmp_path / "lifecycle" / "intelliagent.db")
    db = DatabaseManager(db_path)
    await db.initialize()
    await db.create_conversation(conversation_id="conversation-1", title="测试 Conversation", task="测试任务")

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
    assert runtime.create_engine.return_value.last_max_iterations == 3
    assert runtime.create_engine.return_value.last_history_context is None


async def test_run_service_passes_conversation_history_to_engine(tmp_path):
    db_path = str(tmp_path / "history" / "intelliagent.db")
    db = DatabaseManager(db_path)
    await db.initialize()
    await db.create_conversation(conversation_id="conversation-history", title="历史", task="旧任务")
    await db.save_message("conversation-history", "assistant", "历史答案")

    runtime = Mock()
    runtime.create_engine.return_value = FakeSuccessfulEngine()
    service = RunService(runtime, db_manager=db)

    await service.run_task_async(
        task="新任务",
        max_iterations=3,
        conversation_id="conversation-history",
    )

    assert runtime.create_engine.return_value.last_history_context is not None
    assert "历史答案" in runtime.create_engine.return_value.last_history_context


async def test_run_service_cancel_run_sets_cancel_requested_flag(tmp_path):
    db_path = str(tmp_path / "cancel" / "intelliagent.db")
    db = DatabaseManager(db_path)
    await db.initialize()
    await db.create_conversation(conversation_id="conversation-4", title="取消 Conversation")

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
    await db.create_conversation(conversation_id="conversation-a", title="A", task="任务 A")
    await db.create_conversation(conversation_id="conversation-b", title="B", task="任务 B")

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
        assert "不属于当前 Conversation" in str(exc)
    else:
        raise AssertionError("应拒绝跨 Conversation 使用 source_run_id")

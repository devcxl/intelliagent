#!/usr/bin/env python3
"""PR4 run 生命周期集成测试。"""

from unittest.mock import Mock

from src.db import DatabaseSessionManager
from src.services import RunService
from src.web.database import DatabaseManager


class FakeSuccessfulEngine:
    def __init__(self):
        self.last_kwargs = None
        self.last_task = None

    async def iter_steps(self, task, max_iterations=None, **kwargs):
        self.last_task = task
        self.last_kwargs = kwargs
        yield {
            "type": "thought",
            "iteration": 1,
            "data": {"reasoning": "先读取文件", "is_complete": False},
        }
        yield {
            "type": "action",
            "iteration": 1,
            "data": {"tool": "read_file", "args": {"path": "demo.txt"}},
        }
        observation = {
            "iteration": 1,
            "tool_name": "read_file",
            "tool_args": {"path": "demo.txt"},
            "result": {"status": "ok", "content": "demo"},
            "status": "success",
            "error": None,
            "execution_time": 0.01,
        }
        yield {
            "type": "observation",
            "iteration": 1,
            "data": observation,
        }
        yield {
            "type": "answer",
            "iteration": 2,
            "data": {"answer": "done"},
        }


async def test_run_service_persists_run_messages_and_traces(tmp_path):
    db_path = tmp_path / "lifecycle" / "intelliagent.db"
    await DatabaseManager(str(db_path)).initialize()

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    await DatabaseManager(str(db_path)).create_session(
        session_id="conversation-1",
        title="测试会话",
        task="测试任务",
        status="idle",
    )

    runtime = Mock()
    runtime.create_engine.return_value = FakeSuccessfulEngine()
    service = RunService(runtime, session_manager=session_manager)

    result = await service.run_task_async(
        task="测试任务",
        max_iterations=3,
        conversation_id="conversation-1",
    )

    assert result["success"] is True
    run = await service.run_repository.get(result["run_id"])
    assert run is not None
    assert run.status == "completed"
    assert run.current_iteration == 2

    traces = await service.trace_repository.list_by_run(run.id)
    assert [trace.type for trace in traces] == ["thought", "action", "observation", "answer"]

    messages = await service.message_repository.list_by_conversation("conversation-1")
    assert [message.role for message in messages] == ["user", "assistant"]


async def test_run_service_resume_reuses_existing_run_and_observations(tmp_path):
    db_path = tmp_path / "resume" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()
    await manager.create_session(
        session_id="conversation-2",
        title="恢复会话",
        task="恢复任务",
        status="idle",
    )

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    engine = FakeSuccessfulEngine()
    runtime = Mock()
    runtime.create_engine.return_value = engine
    service = RunService(runtime, session_manager=session_manager)

    run = await service.run_repository.create(
        run_id="run-cancelled",
        conversation_id="conversation-2",
        task_snapshot="恢复任务",
        status="cancelled",
        max_iterations=3,
        current_iteration=1,
    )
    await service.trace_repository.create(
        trace_id="trace-1",
        run_id=run.id,
        iteration=1,
        trace_type="observation",
        data={
            "iteration": 1,
            "tool_name": "read_file",
            "tool_args": {"path": "resume.txt"},
            "result": {"status": "ok", "content": "resume"},
            "status": "success",
            "error": None,
            "execution_time": 0.01,
        },
    )

    result = await service.resume("run-cancelled")

    assert result["success"] is True
    resumed_run = await service.run_repository.get("run-cancelled")
    assert resumed_run is not None
    assert resumed_run.status == "completed"
    assert engine.last_kwargs["start_iteration"] == 2
    assert engine.last_kwargs["reset_state"] is False
    assert len(engine.last_kwargs["seed_observations"]) == 1


async def test_run_service_rerun_links_source_run_without_duplicate_user_message(tmp_path):
    db_path = tmp_path / "rerun" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()
    await manager.create_session(
        session_id="conversation-3",
        title="重跑会话",
        task="重跑任务",
        status="idle",
    )

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    runtime = Mock()
    runtime.create_engine.return_value = FakeSuccessfulEngine()
    service = RunService(runtime, session_manager=session_manager)

    first_result = await service.run_task_async(
        task="重跑任务",
        max_iterations=3,
        conversation_id="conversation-3",
    )

    second_result = await service.rerun(
        conversation_id="conversation-3",
        task="重跑任务",
        max_iterations=3,
        source_run_id=first_result["run_id"],
    )

    rerun = await service.run_repository.get(second_result["run_id"])
    assert rerun is not None
    assert rerun.source_run_id == first_result["run_id"]
    assert rerun.task_snapshot == "重跑任务"

    messages = await service.message_repository.list_by_conversation("conversation-3")
    assert [message.role for message in messages] == ["user", "assistant", "assistant"]


async def test_run_service_cancel_run_sets_cancel_requested_flag(tmp_path):
    db_path = tmp_path / "cancel" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()
    await manager.create_session(
        session_id="conversation-4",
        title="取消会话",
        task="取消任务",
        status="idle",
    )

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    runtime = Mock()
    service = RunService(runtime, session_manager=session_manager)

    run = await service.run_repository.create(
        run_id="run-pending",
        conversation_id="conversation-4",
        task_snapshot="取消任务",
        status="running",
        max_iterations=3,
    )

    cancelled = await service.cancel_run(run.id)

    assert cancelled is True
    updated_run = await service.run_repository.get(run.id)
    assert updated_run is not None
    assert updated_run.cancel_requested is True


async def test_run_repository_enforces_single_active_run_per_conversation(tmp_path):
    db_path = tmp_path / "active-run" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()
    await manager.create_session(
        session_id="conversation-5",
        title="唯一活跃 run",
        task="唯一约束",
        status="idle",
    )

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    runtime = Mock()
    service = RunService(runtime, session_manager=session_manager)

    await service.run_repository.create(
        run_id="run-1",
        conversation_id="conversation-5",
        task_snapshot="唯一约束",
        status="running",
        max_iterations=3,
    )

    try:
        await service.run_repository.create(
            run_id="run-2",
            conversation_id="conversation-5",
            task_snapshot="唯一约束",
            status="pending",
            max_iterations=3,
        )
    except ValueError as exc:
        assert "已存在活跃 run" in str(exc)
    else:
        raise AssertionError("应阻止同一会话创建第二个活跃 run")


async def test_rerun_rejects_cross_conversation_source_run(tmp_path):
    db_path = tmp_path / "lineage" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()
    await manager.create_session(
        session_id="conversation-a",
        title="A",
        task="任务 A",
        status="idle",
    )
    await manager.create_session(
        session_id="conversation-b",
        title="B",
        task="任务 B",
        status="idle",
    )

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    runtime = Mock()
    runtime.create_engine.return_value = FakeSuccessfulEngine()
    service = RunService(runtime, session_manager=session_manager)

    source_run = await service.run_repository.create(
        run_id="run-a-1",
        conversation_id="conversation-a",
        task_snapshot="任务 A",
        status="completed",
        max_iterations=3,
    )

    try:
        await service.rerun(
            conversation_id="conversation-b",
            task="任务 B",
            max_iterations=3,
            source_run_id=source_run.id,
        )
    except Exception as exc:
        assert "不属于当前会话" in str(exc)
    else:
        raise AssertionError("应拒绝跨会话使用 source_run_id")


async def test_resume_uses_run_task_snapshot_after_custom_rerun(tmp_path):
    db_path = tmp_path / "task-snapshot" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()
    await manager.create_session(
        session_id="conversation-snapshot",
        title="任务快照",
        task="原始任务",
        status="idle",
    )

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    engine = FakeSuccessfulEngine()
    runtime = Mock()
    runtime.create_engine.return_value = engine
    service = RunService(runtime, session_manager=session_manager)

    await service.run_repository.create(
        run_id="run-snapshot",
        conversation_id="conversation-snapshot",
        task_snapshot="自定义重跑任务",
        status="cancelled",
        max_iterations=3,
        current_iteration=1,
    )
    await service.trace_repository.create(
        trace_id="trace-snapshot",
        run_id="run-snapshot",
        iteration=1,
        trace_type="observation",
        data={
            "iteration": 1,
            "tool_name": "read_file",
            "tool_args": {"path": "snapshot.txt"},
            "result": {"status": "ok", "content": "snapshot"},
            "status": "success",
            "error": None,
            "execution_time": 0.01,
        },
    )

    result = await service.resume("run-snapshot")

    assert result["success"] is True
    assert engine.last_task == "自定义重跑任务"


async def test_resume_rejects_other_active_run_in_same_conversation(tmp_path):
    db_path = tmp_path / "resume-conflict" / "intelliagent.db"
    manager = DatabaseManager(str(db_path))
    await manager.initialize()
    await manager.create_session(
        session_id="conversation-resume-conflict",
        title="恢复冲突",
        task="恢复任务",
        status="idle",
    )

    session_manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    runtime = Mock()
    runtime.create_engine.return_value = FakeSuccessfulEngine()
    service = RunService(runtime, session_manager=session_manager)

    await service.run_repository.create(
        run_id="run-cancelled-1",
        conversation_id="conversation-resume-conflict",
        task_snapshot="恢复任务",
        status="cancelled",
        max_iterations=3,
        current_iteration=1,
    )
    await service.run_repository.create(
        run_id="run-active-2",
        conversation_id="conversation-resume-conflict",
        task_snapshot="恢复任务",
        status="running",
        max_iterations=3,
    )

    try:
        await service.resume("run-cancelled-1")
    except Exception as exc:
        assert "已存在其他活跃 run" in str(exc)
    else:
        raise AssertionError("有其他活跃 run 时不应允许 resume")

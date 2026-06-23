"""TaskRepository 和 task_tools 单元测试。"""

from __future__ import annotations

import json

import pytest

from src.db.manager import DatabaseManager
from src.db.repositories import TaskRepository
from src.tools.task_tools import set_task_context, task_add, task_finish, task_update, task_write


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test_task.db"


@pytest.fixture
async def db_manager(db_path):
    db = DatabaseManager(str(db_path))
    await db.initialize()
    await db.create_conversation("conv-1", title="测试", task="测试任务")
    return db


@pytest.fixture
def task_ctx(db_manager):
    set_task_context(db_manager, "conv-1")
    yield
    set_task_context(None, None)


class TestTaskRepository:
    @pytest.mark.asyncio
    async def test_add_and_get(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        result = await repo.add("conv-1", title="设计API", content="设计REST接口", priority="high")
        assert result["status"] == "pending"
        assert result["id"].startswith("task-")

        task = await repo.get(result["id"])
        assert task is not None
        assert task["title"] == "设计API"
        assert task["content"] == "设计REST接口"
        assert task["priority"] == "high"
        assert task["status"] == "pending"
        assert task["parent_id"] is None
        assert task["completed_at"] is None

    @pytest.mark.asyncio
    async def test_add_with_parent(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        parent = await repo.add("conv-1", title="父任务")
        child = await repo.add("conv-1", title="子任务", parent_id=parent["id"])
        assert child["status"] == "pending"

        task = await repo.get(child["id"])
        assert task is not None
        assert task["parent_id"] == parent["id"]

    @pytest.mark.asyncio
    async def test_list_by_conversation(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        await repo.add("conv-1", title="任务1", sort_order=0)
        await repo.add("conv-1", title="任务2", sort_order=1)
        await repo.add("conv-1", title="任务3", sort_order=2)

        tasks = await repo.list_by_conversation("conv-1")
        assert len(tasks) == 3
        assert tasks[0]["title"] == "任务1"
        assert tasks[1]["title"] == "任务2"
        assert tasks[2]["title"] == "任务3"

    @pytest.mark.asyncio
    async def test_get_not_found(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        assert await repo.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_update_title(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        result = await repo.add("conv-1", title="旧标题")
        await repo.update(result["id"], title="新标题")
        task = await repo.get(result["id"])
        assert task is not None
        assert task["title"] == "新标题"

    @pytest.mark.asyncio
    async def test_update_status_to_completed(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        result = await repo.add("conv-1", title="待完成")
        await repo.update(result["id"], status="completed")
        task = await repo.get(result["id"])
        assert task is not None
        assert task["status"] == "completed"
        assert task["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_update_multiple_fields(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        result = await repo.add("conv-1", title="原始", content="原始内容", priority="low")
        await repo.update(result["id"], title="新标题", priority="high")
        task = await repo.get(result["id"])
        assert task is not None
        assert task["title"] == "新标题"
        assert task["priority"] == "high"
        assert task["content"] == "原始内容"

    @pytest.mark.asyncio
    async def test_delete_by_conversation(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        await repo.add("conv-1", title="任务A")
        await repo.add("conv-1", title="任务B")
        assert len(await repo.list_by_conversation("conv-1")) == 2

        await repo.delete_by_conversation("conv-1")
        assert len(await repo.list_by_conversation("conv-1")) == 0

    @pytest.mark.asyncio
    async def test_isolated_conversations(self, db_manager):
        repo = TaskRepository(str(db_manager.db_path))
        await db_manager.create_conversation("conv-2", title="conv2")
        await repo.add("conv-1", title="conv1任务")
        await repo.add("conv-2", title="conv2任务")
        assert len(await repo.list_by_conversation("conv-1")) == 1
        assert len(await repo.list_by_conversation("conv-2")) == 1


class TestTaskTools:
    @pytest.mark.asyncio
    async def test_task_add_success(self, task_ctx):
        result = await task_add(title="设计API", content="设计REST接口", priority="high")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["id"].startswith("task-")
        assert data["title"] == "设计API"
        assert data["task_status"] == "pending"

    @pytest.mark.asyncio
    async def test_task_add_empty_title(self, task_ctx):
        result = await task_add(title="   ")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "EMPTY_TITLE"

    @pytest.mark.asyncio
    async def test_task_write_batch(self, task_ctx):
        result = await task_write(
            tasks=json.dumps([
                {"title": "任务1", "priority": "high"},
                {"title": "任务2", "content": "描述2"},
                {"title": "任务3", "priority": "low"},
            ])
        )
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["count"] == 3
        assert len(data["tasks"]) == 3
        assert data["tasks"][0]["title"] == "任务1"
        assert data["tasks"][1]["title"] == "任务2"
        assert data["tasks"][2]["title"] == "任务3"

    @pytest.mark.asyncio
    async def test_task_write_invalid_json(self, task_ctx):
        result = await task_write(tasks="not json")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "INVALID_PARAMETERS"

    @pytest.mark.asyncio
    async def test_task_write_not_array(self, task_ctx):
        result = await task_write(tasks='{"key": "value"}')
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "INVALID_PARAMETERS"

    @pytest.mark.asyncio
    async def test_task_update_success(self, task_ctx):
        add_result = json.loads(await task_add(title="旧标题", priority="low"))
        task_id = add_result["id"]

        result = await task_update(id=task_id, title="新标题", priority="high")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["updated"] is True

    @pytest.mark.asyncio
    async def test_task_update_not_found(self, task_ctx):
        result = await task_update(id="nonexistent", title="x")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "TASK_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_task_update_empty_id(self, task_ctx):
        result = await task_update(id="  ", title="x")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "EMPTY_TASK_ID"

    @pytest.mark.asyncio
    async def test_task_finish_success(self, task_ctx):
        add_result = json.loads(await task_add(title="待完成"))
        task_id = add_result["id"]

        result = await task_finish(id=task_id)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["task_status"] == "completed"

    @pytest.mark.asyncio
    async def test_task_finish_not_found(self, task_ctx):
        result = await task_finish(id="nonexistent")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "TASK_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_task_finish_empty_id(self, task_ctx):
        result = await task_finish(id="")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "EMPTY_TASK_ID"

    @pytest.mark.asyncio
    async def test_task_write_skips_items_without_title(self, task_ctx):
        result = await task_write(
            tasks=json.dumps([
                {"title": "有效任务"},
                {"content": "没有标题的项"},
                {"title": "另一个有效任务"},
            ])
        )
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["count"] == 2

    @pytest.mark.asyncio
    async def test_task_update_only_specified_fields(self, task_ctx):
        add_result = json.loads(await task_add(title="原始标题", content="原始内容", priority="high"))
        task_id = add_result["id"]

        # 只改 title
        await task_update(id=task_id, title="新标题")
        result = await task_update(id=task_id, status="in_progress")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["updated"] is True

    @pytest.mark.asyncio
    async def test_no_context_returns_error(self):
        set_task_context(None, None)
        result = await task_add(title="test")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "CONTEXT_NOT_INITIALIZED"

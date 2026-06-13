from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from src.tools.file_tools import edit_file, read_file, write_file


@pytest.fixture
def workspace():
    """创建一个临时工作区用于测试。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.mark.asyncio
async def test_read_file_outside_workspace(workspace):
    result = await read_file("/etc/passwd", workspace_root=workspace)
    data = json.loads(result)
    assert data["status"] == "error"
    assert data["code"] == "PATH_OUTSIDE_WORKSPACE"


@pytest.mark.asyncio
async def test_write_file_outside_workspace(workspace):
    result = await write_file("/tmp/evil.sh", "echo hacked", workspace_root=workspace)
    data = json.loads(result)
    assert data["status"] == "error"
    assert data["code"] == "PATH_OUTSIDE_WORKSPACE"
    assert not pathlib.Path("/tmp/evil.sh").exists()


@pytest.mark.asyncio
async def test_edit_file_outside_workspace(workspace):
    result = await edit_file("../outside.txt", "a", "b", workspace_root=workspace)
    data = json.loads(result)
    assert data["status"] == "error"
    assert data["code"] == "PATH_OUTSIDE_WORKSPACE"


@pytest.mark.asyncio
async def test_read_file_inside_workspace(workspace):
    # 在工作区内创建测试文件
    test_file = pathlib.Path(workspace) / "test.txt"
    test_file.write_text("hello world")

    result = await read_file(str(test_file), workspace_root=workspace)
    data = json.loads(result)
    assert data["status"] == "ok"
    assert "hello world" in data["content"]


@pytest.mark.asyncio
async def test_write_file_inside_workspace(workspace):
    test_file = pathlib.Path(workspace) / "new_file.txt"
    result = await write_file(str(test_file), "test content", workspace_root=workspace)
    data = json.loads(result)
    assert data["status"] == "ok"
    assert test_file.exists()
    assert test_file.read_text() == "test content"


@pytest.mark.asyncio
async def test_edit_file_inside_workspace(workspace):
    test_file = pathlib.Path(workspace) / "edit_test.txt"
    test_file.write_text("old content")

    result = await edit_file(str(test_file), "old", "new", workspace_root=workspace)
    data = json.loads(result)
    assert data["status"] == "ok"
    assert test_file.read_text() == "new content"


@pytest.mark.asyncio
async def test_workspace_root_none_allows_any_path():
    """workspace_root=None 表示不校验，保持向后兼容。"""
    result = await read_file("/etc/passwd", workspace_root=None)
    data = json.loads(result)
    # 文件不存在于测试环境？或者只检查不报边界错误
    assert data.get("code") != "PATH_OUTSIDE_WORKSPACE"


@pytest.mark.asyncio
async def test_workspace_root_env_var(workspace, monkeypatch):
    """INTELLIAGENT_WORKSPACE_ROOT 环境变量应激活边界校验。"""
    monkeypatch.setenv("INTELLIAGENT_WORKSPACE_ROOT", workspace)
    result = await read_file("/etc/passwd")
    data = json.loads(result)
    assert data["status"] == "error"
    assert data["code"] == "PATH_OUTSIDE_WORKSPACE"

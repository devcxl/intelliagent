#!/usr/bin/env python3
"""
工具执行 DEBUG 日志测试

使用 caplog fixture 验证工具层的 DEBUG 级别日志输出。
"""

import logging
import tempfile
from pathlib import Path

import pytest

from src.db.engine import create_engine, create_session_factory, init_db
from src.db.models import Conversation
from src.db.repositories import ConversationRepository
from src.tools.file_tools import edit_file, read_file, write_file
from src.tools.registry import ToolRegistryFactory
from src.tools.shell_tool import run_shell


class TestToolRegistryDebugLogs:
    @pytest.fixture(autouse=True)
    async def setup_task_context(self, tmp_path):
        db_path = tmp_path / "test.db"
        engine = create_engine(str(db_path))
        await init_db(engine)
        factory = create_session_factory(engine)
        async with factory() as session:
            conv_repo = ConversationRepository(session)
            await conv_repo.save(Conversation(id="conv-test", title="test"))
        self.registry = ToolRegistryFactory(
            session_factory_provider=lambda: factory,
            conversation_id_provider=lambda: "conv-test",
            agent_id="agent-001",
        ).create_default()
        yield
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_call_tool_logs_tool_name_and_args_len(self, caplog):
        """ToolRegistry.call_tool() 输出 tool_name 和 args_len"""
        caplog.set_level(logging.DEBUG, logger="intelliagent")
        await self.registry.call_tool("task_write", tasks='[{"title":"test","priority":"high"}]')

        assert "ToolRegistry - 调用工具" in caplog.text
        assert "tool=task_write" in caplog.text
        assert "args_len=1" in caplog.text


class TestShellToolDebugLogs:
    @pytest.mark.asyncio
    async def test_run_shell_logs_command_and_returncode(self, caplog):
        """ShellTool.run_shell() 输出命令、执行时间、返回码"""
        caplog.set_level(logging.DEBUG, logger="intelliagent")
        await run_shell("echo hello")

        assert "ShellTool - 执行命令" in caplog.text
        assert "cmd=echo hello" in caplog.text
        assert "time_ms=" in caplog.text
        assert "returncode=0" in caplog.text


class TestFileToolsDebugLogs:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        yield
        self.temp_dir.cleanup()

    @pytest.mark.asyncio
    async def test_read_file_logs_path_and_size(self, caplog):
        """FileTools.read_file() 输出 path 和 size"""
        caplog.set_level(logging.DEBUG, logger="intelliagent")
        test_file = Path(self.temp_dir.name) / "read_test.txt"
        test_file.write_text("hello world")

        await read_file(str(test_file))

        assert "FileTools - 读取文件" in caplog.text
        assert f"path={test_file}" in caplog.text
        assert "size=11" in caplog.text

    @pytest.mark.asyncio
    async def test_write_file_logs_path_and_size(self, caplog):
        """FileTools.write_file() 输出 path 和 size"""
        caplog.set_level(logging.DEBUG, logger="intelliagent")
        test_file = Path(self.temp_dir.name) / "write_test.txt"

        await write_file(str(test_file), "hello world")

        assert "FileTools - 写入文件" in caplog.text
        assert f"path={test_file}" in caplog.text
        assert "size=11" in caplog.text

    @pytest.mark.asyncio
    async def test_edit_file_logs_path_and_result(self, caplog):
        """FileTools.edit_file() 输出 path 和替换数"""
        caplog.set_level(logging.DEBUG, logger="intelliagent")
        test_file = Path(self.temp_dir.name) / "edit_test.txt"
        test_file.write_text("hello world")

        await edit_file(str(test_file), "hello", "hi")

        assert "FileTools - 编辑文件" in caplog.text
        assert f"path={test_file}" in caplog.text
        assert "replacements=1" in caplog.text

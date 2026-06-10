#!/usr/bin/env python3
"""
内置工具单元测试

测试所有内置工具的功能和错误处理。
这些测试会真实执行工具操作，不使用 mock。
"""
import asyncio
import json
import tempfile
import sys
import os
import pytest
from pathlib import Path
from typing import Dict, Any

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import logger


def load_tool_from_mcp_server():
    """从 mcp_server.py 加载工具函数
    
    由于 mcp 框架的特殊性，直接导入工具函数可能有问题，
    因此这里通过执行子进程的方式测试，或直接导入模块
    """
    try:
        # 尝试导入 mcp_server 模块
        import mcp_server
        return mcp_server
    except ImportError as e:
        logger.warning(f"无法导入 mcp_server: {e}")
        return None


@pytest.mark.asyncio
class TestBuiltinTools:
    """内置工具测试类"""
    
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """测试前准备和清理"""
        # 创建临时目录用于测试文件操作
        self.temp_dir = tempfile.TemporaryDirectory()
        logger.info(f"✅ 创建临时测试目录: {self.temp_dir.name}")
        
        yield
        
        # 测试后清理
        if self.temp_dir:
            self.temp_dir.cleanup()
            logger.info("🧹 清理临时测试目录")
    
    def _parse_json_response(self, response_str: str) -> Dict[str, Any]:
        """解析工具响应（JSON 格式）"""
        return json.loads(response_str)
    
    async def test_run_shell_success(self):
        """测试 run_shell - 成功情况"""
        logger.info("\n🧪 测试 run_shell 成功情况...")
        from src.tools.builtin_tools import run_shell
        
        result = await run_shell("echo 'Hello World'")
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", f"期望 status=ok，得到 {data['status']}"
        assert "Hello World" in data["output"], f"输出不匹配: {data['output']}"
        assert data["returncode"] == 0, f"返回码应为 0，得到 {data['returncode']}"
        logger.info(f"✅ 通过: run_shell 成功执行命令")
    
    async def test_run_shell_empty_command(self):
        """测试 run_shell - 空命令"""
        logger.info("\n🧪 测试 run_shell 空命令...")
        from src.tools.builtin_tools import run_shell
        
        result = await run_shell("")
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误状态"
        assert data["code"] == "EMPTY_COMMAND", f"错误代码应为 EMPTY_COMMAND，得到 {data['code']}"
        logger.info(f"✅ 通过: run_shell 正确拒绝空命令")
    
    async def test_run_shell_with_pipe(self):
        """测试 run_shell - 复杂命令（管道）"""
        logger.info("\n🧪 测试 run_shell 管道命令...")
        from src.tools.builtin_tools import run_shell
        
        result = await run_shell("printf '1\\n2\\n3\\n' | wc -l")
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "管道命令应该成功"
        assert "3" in data["output"].strip(), f"输出应包含 3，得到 {data['output']}"
        logger.info(f"✅ 通过: run_shell 支持管道操作")
    
    async def test_read_file_success(self):
        """测试 read_file - 成功读取"""
        logger.info("\n🧪 测试 read_file 成功读取...")
        from src.tools.builtin_tools import read_file, write_file
        
        # 先写入测试文件
        test_file = Path(self.temp_dir.name) / "test.txt"
        test_content = "Hello World\nLine 2"
        await write_file(str(test_file), test_content)
        
        # 读取文件
        result = await read_file(str(test_file))
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", f"应该成功读取，得到 {data['status']}"
        assert test_content in data["content"], f"内容不匹配: {data['content']}"
        assert data["truncated"] == False, "小文件不应被截断"
        logger.info(f"✅ 通过: read_file 成功读取文件")
    
    async def test_read_file_not_found(self):
        """测试 read_file - 文件不存在"""
        logger.info("\n🧪 测试 read_file 文件不存在...")
        from src.tools.builtin_tools import read_file
        
        result = await read_file("/nonexistent/file.txt")
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误"
        assert data["code"] == "FILE_NOT_FOUND", f"应该是 FILE_NOT_FOUND，得到 {data['code']}"
        logger.info(f"✅ 通过: read_file 正确处理不存在的文件")
    
    async def test_write_file_success(self):
        """测试 write_file - 成功写入"""
        logger.info("\n🧪 测试 write_file 成功写入...")
        from src.tools.builtin_tools import write_file
        
        test_file = Path(self.temp_dir.name) / "output.txt"
        content = "Test Content"
        
        result = await write_file(str(test_file), content)
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", f"应该成功写入，得到 {data['status']}"
        assert test_file.exists(), "文件应该被创建"
        
        # 验证文件内容
        actual_content = test_file.read_text()
        assert actual_content == content, f"文件内容不匹配: {actual_content}"
        logger.info(f"✅ 通过: write_file 成功创建文件")
    
    async def test_write_file_create_parents(self):
        """测试 write_file - 自动创建父目录"""
        logger.info("\n🧪 测试 write_file 自动创建父目录...")
        from src.tools.builtin_tools import write_file
        
        test_file = Path(self.temp_dir.name) / "subdir" / "nested" / "file.txt"
        content = "Nested Content"
        
        result = await write_file(str(test_file), content)
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "应该成功写入"
        assert test_file.exists(), "文件应该被创建，包括父目录"
        logger.info(f"✅ 通过: write_file 自动创建父目录")
    
    async def test_list_dir_success(self):
        """测试 list_dir - 列出目录"""
        logger.info("\n🧪 测试 list_dir 列出目录...")
        from src.tools.builtin_tools import list_dir, write_file
        
        # 创建测试文件
        (Path(self.temp_dir.name) / "file1.txt").write_text("content1")
        (Path(self.temp_dir.name) / "file2.txt").write_text("content2")
        (Path(self.temp_dir.name) / "subdir").mkdir()
        
        result = await list_dir(self.temp_dir.name)
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "应该成功列出目录"
        assert data["count"] >= 3, f"应该至少有 3 个项目，得到 {data['count']}"
        assert any(item["name"] == "file1.txt" for item in data["items"]), "应该包含 file1.txt"
        assert any(item["name"] == "subdir" for item in data["items"]), "应该包含 subdir"
        logger.info(f"✅ 通过: list_dir 成功列出目录（{data['count']} 项）")
    
    async def test_list_dir_not_found(self):
        """测试 list_dir - 目录不存在"""
        logger.info("\n🧪 测试 list_dir 目录不存在...")
        from src.tools.builtin_tools import list_dir
        
        result = await list_dir("/nonexistent/directory")
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误"
        assert data["code"] == "NOT_FOUND", f"应该是 NOT_FOUND，得到 {data['code']}"
        logger.info(f"✅ 通过: list_dir 正确处理不存在的目录")
    
    async def test_delete_file_success(self):
        """测试 delete_file - 成功删除"""
        logger.info("\n🧪 测试 delete_file 成功删除...")
        from src.tools.builtin_tools import delete_file, write_file
        
        test_file = Path(self.temp_dir.name) / "to_delete.txt"
        
        # 先创建文件
        await write_file(str(test_file), "to be deleted")
        assert test_file.exists(), "文件应该被创建"
        
        # 删除文件
        result = await delete_file(str(test_file))
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "应该成功删除"
        assert not test_file.exists(), "文件应该被删除"
        logger.info(f"✅ 通过: delete_file 成功删除文件")
    
    async def test_delete_file_not_found(self):
        """测试 delete_file - 文件不存在"""
        logger.info("\n🧪 测试 delete_file 文件不存在...")
        from src.tools.builtin_tools import delete_file
        
        result = await delete_file("/nonexistent/file.txt")
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误"
        assert data["code"] == "FILE_NOT_FOUND", f"应该是 FILE_NOT_FOUND，得到 {data['code']}"
        logger.info(f"✅ 通过: delete_file 正确处理不存在的文件")
    
    async def test_file_exists_file(self):
        """测试 file_exists - 文件存在"""
        logger.info("\n🧪 测试 file_exists 文件存在...")
        from src.tools.builtin_tools import file_exists, write_file
        
        test_file = Path(self.temp_dir.name) / "exists.txt"
        await write_file(str(test_file), "exists")
        
        result = await file_exists(str(test_file))
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "应该成功检查"
        assert data["exists"] == True, "文件应该存在"
        assert data["type"] == "file", f"类型应该是 file，得到 {data['type']}"
        logger.info(f"✅ 通过: file_exists 正确识别存在的文件")
    
    async def test_file_exists_directory(self):
        """测试 file_exists - 目录存在"""
        logger.info("\n🧪 测试 file_exists 目录存在...")
        from src.tools.builtin_tools import file_exists
        
        result = await file_exists(self.temp_dir.name)
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "应该成功检查"
        assert data["exists"] == True, "目录应该存在"
        assert data["type"] == "directory", f"类型应该是 directory，得到 {data['type']}"
        logger.info(f"✅ 通过: file_exists 正确识别目录")
    
    async def test_file_exists_not_found(self):
        """测试 file_exists - 不存在"""
        logger.info("\n🧪 测试 file_exists 不存在...")
        from src.tools.builtin_tools import file_exists
        
        result = await file_exists("/nonexistent/path")
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "应该成功检查"
        assert data["exists"] == False, "路径应该不存在"
        logger.info(f"✅ 通过: file_exists 正确识别不存在的路径")
    
    async def test_edit_file_single_replacement(self):
        """测试 edit_file - 单次替换成功"""
        logger.info("\n🧪 测试 edit_file 单次替换...")
        from src.tools.builtin_tools import edit_file, write_file
        
        test_file = Path(self.temp_dir.name) / "edit_test.txt"
        original_content = "Hello World\nHello Again\n"
        await write_file(str(test_file), original_content)
        
        result = await edit_file(str(test_file), "Hello World", "Hi World")
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", f"应该成功编辑，得到 {data['status']}"
        assert data["replacements"] == 1, f"应该替换 1 处，得到 {data['replacements']}"
        
        actual_content = test_file.read_text()
        assert "Hi World" in actual_content, "新内容应该存在"
        assert "Hello Again" in actual_content, "未替换的内容应该保持不变"
        logger.info(f"✅ 通过: edit_file 单次替换成功")
    
    async def test_edit_file_replace_all(self):
        """测试 edit_file - 全局替换"""
        logger.info("\n🧪 测试 edit_file 全局替换...")
        from src.tools.builtin_tools import edit_file, write_file
        
        test_file = Path(self.temp_dir.name) / "replace_all.txt"
        original_content = "old_value\nold_value\nold_value\n"
        await write_file(str(test_file), original_content)
        
        result = await edit_file(str(test_file), "old_value", "new_value", replaceAll=True)
        data = self._parse_json_response(result)
        
        assert data["status"] == "ok", "应该成功编辑"
        assert data["replacements"] == 3, f"应该替换 3 处，得到 {data['replacements']}"
        
        actual_content = test_file.read_text()
        assert actual_content == "new_value\nnew_value\nnew_value\n", "所有匹配都应该被替换"
        logger.info(f"✅ 通过: edit_file 全局替换成功（{data['replacements']} 处）")
    
    async def test_edit_file_old_string_not_found(self):
        """测试 edit_file - 旧字符串未找到"""
        logger.info("\n🧪 测试 edit_file 旧字符串未找到...")
        from src.tools.builtin_tools import edit_file, write_file
        
        test_file = Path(self.temp_dir.name) / "not_found.txt"
        await write_file(str(test_file), "Some content here")
        
        result = await edit_file(str(test_file), "nonexistent", "replacement")
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误"
        assert data["code"] == "OLD_STRING_NOT_FOUND", f"错误代码应为 OLD_STRING_NOT_FOUND，得到 {data['code']}"
        logger.info(f"✅ 通过: edit_file 正确处理未找到的旧字符串")
    
    async def test_edit_file_multiple_matches_without_replace_all(self):
        """测试 edit_file - 多个匹配但未启用 replaceAll"""
        logger.info("\n🧪 测试 edit_file 多个匹配但未启用 replaceAll...")
        from src.tools.builtin_tools import edit_file, write_file
        
        test_file = Path(self.temp_dir.name) / "multiple.txt"
        original_content = "repeat\nrepeat\nrepeat\n"
        await write_file(str(test_file), original_content)
        
        result = await edit_file(str(test_file), "repeat", "replaced", replaceAll=False)
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误"
        assert data["code"] == "MULTIPLE_MATCHES", f"错误代码应为 MULTIPLE_MATCHES，得到 {data['code']}"
        logger.info(f"✅ 通过: edit_file 正确拒绝多匹配单次替换")
    
    async def test_edit_file_empty_old_string(self):
        """测试 edit_file - 空 oldString"""
        logger.info("\n🧪 测试 edit_file 空 oldString...")
        from src.tools.builtin_tools import edit_file
        
        result = await edit_file("dummy.txt", "", "new_value")
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误"
        assert data["code"] == "EMPTY_OLD_STRING", f"错误代码应为 EMPTY_OLD_STRING，得到 {data['code']}"
        logger.info(f"✅ 通过: edit_file 正确拒绝空 oldString")
    
    async def test_edit_file_file_not_exists(self):
        """测试 edit_file - 文件不存在"""
        logger.info("\n🧪 测试 edit_file 文件不存在...")
        from src.tools.builtin_tools import edit_file
        
        result = await edit_file("/nonexistent/file.txt", "old", "new")
        data = self._parse_json_response(result)
        
        assert data["status"] == "error", "应该返回错误"
        assert data["code"] == "FILE_NOT_FOUND", f"错误代码应为 FILE_NOT_FOUND，得到 {data['code']}"
        logger.info(f"✅ 通过: edit_file 正确处理不存在的文件")

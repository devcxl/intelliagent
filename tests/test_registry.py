#!/usr/bin/env python3
"""
MCP 工具注册中心测试脚本
验证 MCP Server 和工具注册中心是否正常工作
"""
import sys
from core.tool_registry import ToolRegistry
from utils.logger import logger


def test_tool_registry():
    """测试工具注册中心"""
    logger.info("=" * 60)
    logger.info("开始测试 MCP 工具注册中心")
    logger.info("=" * 60)

    try:
        # 初始化工具注册中心
        logger.info("\n1. 初始化工具注册中心...")
        registry = ToolRegistry()
        registry.initialize()

        # 列出所有可用工具
        logger.info("\n2. 列出所有可用工具...")
        tools = registry.list_tools()
        logger.info(f"可用工具: {tools}")

        # 描述所有工具
        logger.info("\n3. 工具详细描述:")
        descriptions = registry.describe_tools()
        print(descriptions)

        # 测试 shell 命令
        logger.info("\n4. 测试 run_shell 工具...")
        shell_tool = registry.get_tool("run_shell")
        result = shell_tool(cmd="echo 'Hello from MCP!'")
        logger.info(f"执行结果: {result}")

        # 测试文件写入
        logger.info("\n5. 测试 write_file 工具...")
        write_tool = registry.get_tool("write_file")
        result = write_tool(path="/tmp/test_mcp.txt", content="MCP 测试内容")
        logger.info(f"写入结果: {result}")

        # 测试文件读取
        logger.info("\n6. 测试 read_file 工具...")
        read_tool = registry.get_tool("read_file")
        result = read_tool(path="/tmp/test_mcp.txt")
        logger.info(f"读取结果: {result}")

        # 清理资源
        logger.info("\n7. 清理资源...")
        registry.cleanup()

        logger.info("\n" + "=" * 60)
        logger.info("✅ 所有测试通过！")
        logger.info("=" * 60)

        assert True

    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        assert False


if __name__ == "__main__":
    test_tool_registry()

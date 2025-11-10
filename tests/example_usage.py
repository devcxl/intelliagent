#!/usr/bin/env python3
"""
MCP 工具注册中心快速示例
展示如何使用完全 MCP 模式的工具注册中心
"""
import os
import sys
from pathlib import Path

# 确保可直接运行: 将项目根目录加入 sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tool_registry import ToolRegistry
from utils.logger import logger


def main():
    """主函数"""
    logger.info("=== MCP 工具注册中心快速示例 ===\n")

    # 1. 创建工具注册中心
    logger.info("步骤 1: 创建工具注册中心")
    registry = ToolRegistry()

    try:
        # 2. 初始化（连接到 MCP Server）
        logger.info("步骤 2: 初始化并连接到 MCP Server")
        registry.initialize()

        # 3. 列出可用工具
        logger.info("\n步骤 3: 列出所有可用工具")
        tools = registry.list_tools()
        for tool_name in tools:
            logger.info(f"  - {tool_name}")

        # 4. 使用 shell 工具
        logger.info("\n步骤 4: 执行 shell 命令")
        shell = registry.get_tool("run_shell")
        result = shell(cmd="echo 'Hello from MCP!'")
        logger.info(f"结果: {result.get('output', '')}")

        # 5. 使用文件工具
        logger.info("\n步骤 5: 测试文件读写")

        # 写入文件
        write = registry.get_tool("write_file")
        write(path="/tmp/mcp_demo.txt", content="这是一个 MCP 测试文件\n第二行内容")
        logger.info("文件已写入: /tmp/mcp_demo.txt")

        # 读取文件
        read = registry.get_tool("read_file")
        file_result = read(path="/tmp/mcp_demo.txt")
        logger.info(f"文件内容:\n{file_result.get('content', '')}")

        logger.info("\n✅ 示例运行成功！")

    except Exception as e:
        logger.error(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 6. 清理资源
        logger.info("\n步骤 6: 清理资源")
        registry.cleanup()
        logger.info("资源已清理")


if __name__ == "__main__":
    main()

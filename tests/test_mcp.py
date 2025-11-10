#!/usr/bin/env python3
"""
MCP 集成测试脚本
验证 MCP 工具服务器和客户端是否正常工作
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.tool_registry import ToolRegistry
from utils.logger import logger
import os


def test_mcp_integration():
    """测试 MCP 集成"""
    print("=" * 60)
    print("🧪 MCP 集成测试")
    print("=" * 60)

    # 1. 初始化 ToolRegistry
    print("\n1️⃣ 初始化 ToolRegistry (MCP 客户端)...")
    try:
        tools = ToolRegistry()
        print("   ✅ ToolRegistry 初始化成功")
    except Exception as e:
        print(f"   ❌ 初始化失败: {e}")
        return False

    # 2. 测试 describe_tools
    print("\n2️⃣ 测试 describe_tools()...")
    try:
        descriptions = tools.describe_tools()
        print("   📋 可用工具列表:")
        for line in descriptions.split('\n'):
            print(f"      {line}")
        print("   ✅ describe_tools() 正常")
    except Exception as e:
        print(f"   ❌ describe_tools() 失败: {e}")
        tools.cleanup()
        return False

    # 3. 测试 get_tool
    print("\n3️⃣ 测试 get_tool()...")
    try:
        shell_tool = tools.get_tool("run_shell")
        if shell_tool:
            print(f"   ✅ 获取到工具: run_shell")
        else:
            print("   ❌ 工具不存在")
            tools.cleanup()
            assert False
    except Exception as e:
        print(f"   ❌ get_tool() 失败: {e}")
        tools.cleanup()
        assert False

    # 4. 测试工具执行 - echo 命令
    print("\n4️⃣ 测试工具执行 (run_shell - echo)...")
    try:
        result = shell_tool(cmd="echo 'Hello MCP!'")
        print(f"   📤 执行结果: {result}")
        assert result.get("status") == "ok"
        print("   ✅ run_shell 执行成功")
    except Exception as e:
        print(f"   ❌ 工具执行失败: {e}")
        tools.cleanup()
        assert False

    # 5. 测试 read_file 工具
    print("\n5️⃣ 测试 read_file 工具...")
    try:
        read_tool = tools.get_tool("read_file")
        # 读取 requirements.txt
        result = read_tool(path="requirements.txt")
        print(f"   📤 执行结果状态: {result.get('status')}")
        assert result.get("status") == "ok"
        content = result.get("content", "")
        print(f"   📄 读取内容预览: {content[:100]}...")
        print("   ✅ read_file 执行成功")
    except Exception as e:
        print(f"   ❌ read_file 测试失败: {e}")
        assert False

    # 6. 测试 write_file 工具
    print("\n6️⃣ 测试 write_file 工具...")
    try:
        write_tool = tools.get_tool("write_file")
        test_file = "/tmp/mcp_test.txt"
        test_content = "MCP Integration Test - " + str(os.getpid())

        result = write_tool(path=test_file, content=test_content)

        print(f"   📤 执行结果: {result}")
        assert result.get("status") == "ok"
        # 验证文件是否真的写入
        assert os.path.exists(test_file)
        with open(test_file, 'r') as f:
            actual_content = f.read()
        assert actual_content == test_content
        print("   ✅ write_file 执行成功，内容验证通过")
        os.remove(test_file)
    except Exception as e:
        print(f"   ❌ write_file 测试失败: {e}")
        assert False

    # 7. 清理资源
    print("\n7️⃣ 清理资源...")
    try:
        tools.cleanup()
        print("   ✅ 资源清理成功")
    except Exception as e:
        print(f"   ⚠️  清理时出现警告: {e}")

    print("\n" + "=" * 60)
    print("✅ MCP 集成测试完成！")
    print("=" * 60)

    assert True


if __name__ == "__main__":
    try:
        success = test_mcp_integration()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

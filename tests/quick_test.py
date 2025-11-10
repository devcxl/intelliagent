#!/usr/bin/env python3
"""简单验证脚本"""
import sys
sys.path.insert(0, '.')

print("1. 导入 ToolRegistry...")
from core.tool_registry import ToolRegistry

print("2. 创建实例...")
tr = ToolRegistry()

print("3. 检查工具...")
tools_desc = tr.describe_tools()
print(f"✅ 工具列表:\n{tools_desc}")

print("4. 测试获取工具...")
shell_tool = tr.get_tool("run_shell")
print(f"✅ run_shell 工具: {shell_tool}")

print("\n✅ 所有检查通过！")


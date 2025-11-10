#!/usr/bin/env python3
"""
项目结构验证脚本
验证整理后的项目结构是否正确
"""
import os
import sys

def check_file_exists(filepath, description):
    """检查文件是否存在"""
    exists = os.path.exists(filepath)
    status = "✅" if exists else "❌"
    print(f"{status} {description}: {filepath}")
    return exists

def main():
    print("=" * 60)
    print("🔍 项目结构验证")
    print("=" * 60)

    all_pass = True

    # 检查根目录文件
    print("\n📁 根目录文件:")
    all_pass &= check_file_exists("README.md", "项目入口文档")
    all_pass &= check_file_exists("main.py", "主程序")
    all_pass &= check_file_exists("mcp_server.py", "MCP 服务器")
    all_pass &= check_file_exists("requirements.txt", "依赖配置")

    # 检查文档目录
    print("\n📚 docs/ 目录:")
    docs = [
        "docs/INDEX.md",
        "docs/README.md",
        "docs/QUICKREF.md",
        "docs/CHANGELOG.md",
        "docs/MCP_PURE_MODE.md",
        "docs/STRUCTURE_REORGANIZATION.md"
    ]
    for doc in docs:
        check_file_exists(doc, "文档")  # 不计入 all_pass，文档可选

    # 检查测试目录（新 test/ 目录）
    print("\n🧪 test/ 目录:")
    tests = [
        "test/test_registry.py",
        "test/test_mcp.py",
        "test/test_mcp_minimal.py",
        "test/quick_test.py",
    ]
    for test in tests:
        all_pass &= check_file_exists(test, "测试文件")

    # 检查核心模块
    print("\n🔧 core/ 目录:")
    cores = [
        "core/tool_registry.py",
        "core/tool_registry_mcp.py",
        "core/planner.py",
        "core/executor.py"
    ]
    for core in cores:
        all_pass &= check_file_exists(core, "核心模块")

    # 检查工具函数
    print("\n🛠️ utils/ 目录:")
    utils = [
        "utils/logger.py",
        "utils/config.py"
    ]
    for util in utils:
        all_pass &= check_file_exists(util, "工具函数")

    # 统计
    print("\n" + "=" * 60)
    if all_pass:
        print("✅ 所有检查通过！项目结构正确")
    else:
        print("❌ 部分检查失败，请检查文件是否缺失")
    print("=" * 60)

    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())

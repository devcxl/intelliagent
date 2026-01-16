#!/usr/bin/env python3
"""
IntelliAgent 工具系统使用示例

本文件演示如何在实际项目中使用 IntelliAgent 提供的内置工具。
展示 6 个工具的典型使用场景：run_shell, read_file, write_file, 
list_dir, delete_file, file_exists
"""

import asyncio
from pathlib import Path


async def example_1_basic_shell_commands():
    """示例 1: 执行 Shell 命令
    
    使用场景：
    - 运行系统命令
    - 执行编译、测试、构建任务
    - 调用第三方工具或脚本
    """
    print("\n" + "="*60)
    print("示例 1: 执行 Shell 命令")
    print("="*60)
    
    from mcp_server import run_shell
    
    # 获取当前目录文件列表
    print("\n1️⃣ 列出当前目录文件:")
    result = await run_shell("ls -lh")
    print(f"命令输出: {result[:200]}...")
    
    # 运行 Python 代码
    print("\n2️⃣ 执行 Python 计算:")
    result = await run_shell("python3 -c 'print(\"2+2=\", 2+2)'")
    print(f"命令输出: {result}")
    
    # 查看系统信息
    print("\n3️⃣ 查看系统信息:")
    result = await run_shell("uname -a")
    print(f"系统信息: {result}")


async def example_2_file_operations():
    """示例 2: 文件操作
    
    使用场景：
    - 读取配置文件、日志文件
    - 修改源代码文件
    - 创建临时文件进行数据处理
    """
    print("\n" + "="*60)
    print("示例 2: 文件读写操作")
    print("="*60)
    
    from mcp_server import read_file, write_file, file_exists
    
    # 检查文件是否存在
    test_file = "/tmp/example_test.txt"
    print(f"\n1️⃣ 检查文件是否存在: {test_file}")
    result = await file_exists(test_file)
    print(f"检查结果: {result}")
    
    # 写入文件
    print(f"\n2️⃣ 写入文件内容到 {test_file}")
    content = """# 示例配置文件

## 数据库配置
- host: localhost
- port: 5432
- user: admin

## 日志配置
- level: INFO
- format: %(asctime)s - %(name)s - %(levelname)s - %(message)s
"""
    result = await write_file(test_file, content)
    print(f"写入结果: {result}")
    
    # 读取文件
    print(f"\n3️⃣ 读取文件内容:")
    result = await read_file(test_file)
    print(f"文件内容:\n{result}")
    
    # 追加内容
    print(f"\n4️⃣ 追加新内容:")
    append_content = "\n## 添加的新内容\n- feature: 新增支持多语言\n- version: 2.0.0"
    full_content = content + append_content
    result = await write_file(test_file, full_content)
    print(f"追加结果: {result}")


async def example_3_directory_operations():
    """示例 3: 目录操作
    
    使用场景：
    - 浏览目录结构
    - 获取文件列表
    - 递归处理目录中的文件
    """
    print("\n" + "="*60)
    print("示例 3: 目录列表与浏览")
    print("="*60)
    
    from mcp_server import list_dir
    
    # 列出当前目录
    print("\n1️⃣ 列出项目根目录:")
    result = await list_dir(".")
    print(f"目录内容:\n{result}")
    
    # 列出 docs 目录（如果存在）
    print("\n2️⃣ 列出 docs 目录:")
    result = await list_dir("docs")
    if '"status": "ok"' in result:
        print(f"docs 目录内容:\n{result}")
    else:
        print(f"无法列出目录: {result}")
    
    # 列出 test 目录
    print("\n3️⃣ 列出 test 目录:")
    result = await list_dir("test")
    print(f"test 目录内容:\n{result}")


async def example_4_file_management_workflow():
    """示例 4: 完整的文件管理工作流
    
    使用场景：
    - 数据处理流程：创建 → 修改 → 验证 → 删除
    - 配置文件管理：读取旧配置 → 合并新配置 → 写回
    - 备份和恢复流程
    """
    print("\n" + "="*60)
    print("示例 4: 完整的文件管理工作流")
    print("="*60)
    
    from mcp_server import write_file, read_file, delete_file, file_exists
    
    # 创建临时工作目录和文件
    work_dir = "/tmp/intelliagent_example"
    config_file = f"{work_dir}/config.json"
    
    print(f"\n1️⃣ 创建配置文件: {config_file}")
    config_content = """{
  "app_name": "IntelliAgent",
  "version": "1.0.0",
  "debug": true,
  "features": [
    "file_management",
    "shell_execution",
    "directory_browsing"
  ]
}"""
    result = await write_file(config_file, config_content)
    print(f"创建结果: {result}")
    
    # 读取配置文件
    print(f"\n2️⃣ 读取配置文件:")
    result = await read_file(config_file)
    print(f"配置内容:\n{result}")
    
    # 验证文件存在
    print(f"\n3️⃣ 验证文件存在:")
    result = await file_exists(config_file)
    print(f"验证结果: {result}")
    
    # 清理：删除文件
    print(f"\n4️⃣ 删除配置文件:")
    result = await delete_file(config_file)
    print(f"删除结果: {result}")
    
    # 验证文件已删除
    print(f"\n5️⃣ 验证文件已删除:")
    result = await file_exists(config_file)
    print(f"验证结果: {result}")


async def example_5_error_handling():
    """示例 5: 错误处理最佳实践
    
    使用场景：
    - 处理文件不存在的情况
    - 处理权限拒绝
    - 处理命令执行失败
    - 处理大文件限制
    """
    print("\n" + "="*60)
    print("示例 5: 错误处理最佳实践")
    print("="*60)
    
    from mcp_server import read_file, write_file, delete_file
    import json
    
    # 读取不存在的文件
    print("\n1️⃣ 读取不存在的文件:")
    result = await read_file("/nonexistent/file.txt")
    data = json.loads(result)
    print(f"结果状态: {data['status']}")
    print(f"错误信息: {data['error']}")
    print(f"错误代码: {data.get('code', 'N/A')}")
    
    # 向不存在的目录写入文件（会自动创建目录）
    print("\n2️⃣ 向不存在的目录写入文件（自动创建目录）:")
    test_path = "/tmp/nested/dir/test_file.txt"
    result = await write_file(test_path, "自动创建的文件")
    data = json.loads(result)
    print(f"结果: {result}")
    
    # 删除不存在的文件
    print("\n3️⃣ 删除不存在的文件:")
    result = await delete_file("/nonexistent/file.txt")
    data = json.loads(result)
    print(f"结果状态: {data['status']}")
    print(f"错误信息: {data['error']}")
    
    # 向文件写入超大内容（会触发大小限制）
    print("\n4️⃣ 测试大文件限制:")
    huge_content = "x" * (2 * 1024 * 1024)  # 2 MB 内容
    result = await write_file("/tmp/huge_file.txt", huge_content)
    data = json.loads(result)
    print(f"结果: {data['status']}")
    if data['status'] == 'error':
        print(f"错误代码: {data.get('code', 'N/A')}")
        print(f"限制说明: 文件大小不能超过 1MB")


async def example_6_advanced_shell_usage():
    """示例 6: 高级 Shell 命令用法
    
    使用场景：
    - 使用管道处理数据
    - 执行复杂的脚本
    - 后台任务管理
    - 日志和错误输出
    """
    print("\n" + "="*60)
    print("示例 6: 高级 Shell 命令用法")
    print("="*60)
    
    from mcp_server import run_shell
    
    # 使用管道
    print("\n1️⃣ 使用管道过滤数据:")
    result = await run_shell("ls -la | grep '\\.py' | wc -l")
    print(f"项目中的 Python 文件数: {result.strip()}")
    
    # 执行条件命令
    print("\n2️⃣ 执行条件命令（检查文件是否存在）:")
    result = await run_shell("test -f README.md && echo '文件存在' || echo '文件不存在'")
    print(f"检查结果: {result.strip()}")
    
    # 获取环境变量
    print("\n3️⃣ 获取环境变量:")
    result = await run_shell("echo $HOME")
    print(f"HOME 目录: {result.strip()}")
    
    # 执行失败的命令（错误处理）
    print("\n4️⃣ 执行不存在的命令:")
    result = await run_shell("nonexistent_command_xyz")
    print(f"命令执行结果: {result[:200]}...")
    
    # 在特定目录执行命令
    print("\n5️⃣ 在特定目录执行命令:")
    result = await run_shell("cd /tmp && pwd")
    print(f"执行目录: {result.strip()}")


async def example_7_real_world_scenario():
    """示例 7: 真实场景 - 项目初始化和验证
    
    使用场景：
    - 自动化项目初始化
    - 检查项目完整性
    - 生成项目报告
    """
    print("\n" + "="*60)
    print("示例 7: 真实场景 - 项目初始化和验证")
    print("="*60)
    
    from mcp_server import list_dir, read_file, file_exists, run_shell
    import json
    
    # 检查项目结构
    print("\n1️⃣ 检查项目关键文件是否存在:")
    key_files = ["README.md", "requirements.txt", "main.py", "mcp_server.py"]
    
    for filename in key_files:
        exists_result = await file_exists(filename)
        data = json.loads(exists_result)
        status = "✅" if data.get("exists") else "❌"
        print(f"{status} {filename}")
    
    # 读取 README
    print("\n2️⃣ 读取项目 README:")
    result = await read_file("README.md")
    lines = result.split('\n')
    print(f"README 首行: {lines[0]}")
    print(f"总行数: {len(lines)}")
    
    # 列出项目目录结构
    print("\n3️⃣ 项目目录结构:")
    result = await list_dir(".")
    data = json.loads(result)
    if data['status'] == 'ok':
        items = data.get('items', [])
        # 只显示目录
        dirs = [item for item in items if item.get('type') == 'directory']
        print(f"主要目录: {', '.join([d['name'] for d in dirs[:5]])}")
    
    # 运行项目测试
    print("\n4️⃣ 运行项目验证:")
    result = await run_shell("python test/test_tool_validation.py 2>&1 | tail -5")
    print(f"验证结果:\n{result}")


async def main():
    """主函数 - 按顺序运行所有示例"""
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║" + " "*58 + "║")
    print("║" + "  IntelliAgent 工具系统使用示例".center(58) + "║")
    print("║" + " "*58 + "║")
    print("╚" + "="*58 + "╝")
    
    try:
        # 注意：这些示例需要在安装了 mcp 依赖的环境中运行
        # pip install -r requirements.txt
        
        await example_1_basic_shell_commands()
        await example_2_file_operations()
        await example_3_directory_operations()
        await example_4_file_management_workflow()
        await example_5_error_handling()
        await example_6_advanced_shell_usage()
        await example_7_real_world_scenario()
        
        print("\n" + "="*60)
        print("✅ 所有示例执行完成！")
        print("="*60)
        print("\n💡 更多信息请参考:")
        print("  - 工具文档: docs/TOOLS.md")
        print("  - 快速入门: docs/QUICK_START.md")
        print("  - 集成指南: docs/TOOL_INTEGRATION.md")
        print()
        
    except ImportError as e:
        print(f"\n❌ 错误: 缺少依赖 - {e}")
        print("\n请先安装依赖:")
        print("  pip install -r requirements.txt")
        print("\n然后再运行此示例:")
        print("  python example.py")
    except Exception as e:
        print(f"\n❌ 执行出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

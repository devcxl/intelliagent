#!/usr/bin/env python3
"""
IntelliAgent 使用示例
展示如何使用基于 PDCA 循环的智能代理
"""
from main import IntelliAgent
from utils.logger import logger


def example_1_simple_task():
    """示例 1: 简单文件操作任务"""
    print("\n" + "="*80)
    print("📝 示例 1: 创建文件并写入内容")
    print("="*80)

    agent = IntelliAgent()
    
    task = "创建一个名为 test_hello.py 的文件，内容是打印 Hello, PDCA World!"
    result = agent.run(task)
    
    return result


def example_2_complex_task():
    """示例 2: 复杂任务 - 代码生成与测试"""
    print("\n" + "="*80)
    print("🔧 示例 2: 生成代码并运行测试")
    print("="*80)

    agent = IntelliAgent()
    
    task = """
    创建一个 Python 模块 calculator.py，包含加减乘除四个函数，
    然后创建对应的测试文件 test_calculator.py 并运行测试
    """
    result = agent.run(task)
    
    return result


def example_3_git_operations():
    """示例 3: Git 操作"""
    print("\n" + "="*80)
    print("📦 示例 3: Git 状态检查")
    print("="*80)

    agent = IntelliAgent()
    
    task = "检查当前目录的 git 状态，并列出所有未提交的文件"
    result = agent.run(task)
    
    return result


def example_4_with_experience():
    """示例 4: 使用历史经验"""
    print("\n" + "="*80)
    print("🧠 示例 4: 查看历史经验")
    print("="*80)

    agent = IntelliAgent()
    
    # 查看所有经验
    experiences = agent.get_experiences()
    
    print(f"\n找到 {len(experiences)} 条历史经验:")
    for i, exp in enumerate(experiences, 1):
        print(f"\n经验 {i}:")
        print(f"  任务: {exp.get('task', '未知')[:60]}...")
        print(f"  状态: {exp.get('final_status')}")
        print(f"  步骤: {exp.get('passed_steps')}/{exp.get('total_steps')}")
        print(f"  得分: {exp.get('average_score', 0):.2f}")
        print(f"  时间: {exp.get('timestamp', '未知')}")


def example_5_custom_config():
    """示例 5: 自定义配置"""
    print("\n" + "="*80)
    print("⚙️  示例 5: 使用自定义配置")
    print("="*80)

    # 自定义配置
    agent = IntelliAgent(
        model="gpt-4o",  # 使用更强大的模型
        max_cycles=5,         # 允许更多循环次数
        max_retry=5           # 允许更多重试次数
    )
    
    task = "分析当前项目的代码结构，并生成一个 README.md 文档"
    result = agent.run(task)
    
    return result


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║                    🤖 IntelliAgent 示例程序                        ║
║                  基于 PDCA 循环的智能代理系统                       ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
    """)

    # 选择要运行的示例
    examples = {
        "1": ("简单文件操作", example_1_simple_task),
        "2": ("复杂代码生成", example_2_complex_task),
        "3": ("Git 操作", example_3_git_operations),
        "4": ("查看历史经验", example_4_with_experience),
        "5": ("自定义配置", example_5_custom_config),
    }

    print("请选择要运行的示例:")
    for key, (name, _) in examples.items():
        print(f"  {key}. {name}")
    print("  q. 退出")

    choice = input("\n请输入选项 (1-5 或 q): ").strip()

    if choice == "q":
        print("再见! 👋")
    elif choice in examples:
        _, example_func = examples[choice]
        try:
            example_func()
        except KeyboardInterrupt:
            print("\n\n⚠️  用户中断执行")
        except Exception as e:
            logger.error(f"示例运行失败 | error={e}")
    else:
        print("❌ 无效选项")

from core.context import ContextManager
from core.executor import Executor
from core.memory import Memory
from core.planner import Planner
from core.tool_registry import ToolRegistry
from utils.logger import logger
from dotenv import load_dotenv

def _print_help(tools: ToolRegistry):
    logger.info("\n💡 指令帮助: \n"
                "help/hel/?                    显示此帮助\n"
                "sh <cmd> / shell <cmd>       执行 Shell 命令\n"
                "read <path>                  读取文件\n"
                "write <path> : <content>     写入文件\n"
                "test [path]                  运行 pytest\n"
                "git commit <message>         Git 提交\n"
                "q / quit / exit              退出程序\n"
                "\n🔧 可用工具:\n" + tools.describe_tools())

def main():
    logger.info("🚀 启动 IntelliAgent")
    load_dotenv()
    context = ContextManager()
    memory = Memory()
    tools = ToolRegistry()
    tools.initialize()  # 确保提前初始化，避免首次延迟
    planner = Planner(tools=tools, context=context)
    executor = Executor(tools=tools, memory=memory)

    try:
        while True:
            user_input = input("\n🧑‍💻 请输入你的指令 (q 退出): ")
            if user_input.lower() in ["q", "quit", "exit"]:
                break

            plan = planner.generate_plan(user_input)
            # 如果是帮助计划，直接显示帮助
            if len(plan) == 1 and plan[0]["tool"] == "none" and plan[0]["goal"] == "显示可用工具与用法":
                _print_help(tools)
                continue

            logger.info(f"📝 任务规划结果: {plan}")
            executor.execute_plan(plan)
    finally:
        logger.info("正在关闭...")
        tools.cleanup()

if __name__ == "__main__":
    main()

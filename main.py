#!/usr/bin/env python3
"""
IntelliAgent - 基于 PDCA 循环的智能代理
主入口文件
"""
import sys
from core.llm_client import LLMClient
from core.planner import Planner
from core.executor import Executor
from core.checker import Checker
from core.actor import Actor
from core.pdca_loop import PDCALoop
from core.memory import Memory
from core.context import ContextManager
from core.tool_registry import ToolRegistry
from utils.config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    MAX_PDCA_CYCLES,
    MAX_RETRY_PER_STEP,
    EXPERIENCE_FILE
)
from utils.logger import logger


class IntelliAgent:
    """智能代理主类"""

    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        max_cycles: int = None,
        max_retry: int = None
    ):
        """
        初始化智能代理

        Args:
            api_key: OpenAI API Key
            model: 使用的模型
            max_cycles: 最大PDCA循环次数
            max_retry: 单步骤最大重试次数
        """
        logger.info("="*60)
        logger.info("🤖 初始化 IntelliAgent 智能代理系统")
        logger.info("="*60)

        # 使用配置或参数
        self.api_key = api_key or OPENAI_API_KEY
        self.model = model or OPENAI_MODEL
        self.max_cycles = max_cycles or MAX_PDCA_CYCLES
        self.max_retry = max_retry or MAX_RETRY_PER_STEP

        # 初始化各个组件
        self._initialize_components()

        logger.info("✅ 智能代理初始化完成")
        logger.info(f"   模型: {self.model}")
        logger.info(f"   最大循环次数: {self.max_cycles}")
        logger.info(f"   单步最大重试: {self.max_retry}")
        logger.info("="*60 + "\n")

    def _initialize_components(self):
        """初始化所有组件"""
        try:
            # 1. LLM 客户端
            logger.info("初始化 LLM 客户端...")
            self.llm_client = LLMClient(api_key=self.api_key, model=self.model)

            # 2. 记忆管理器
            logger.info("初始化记忆管理器...")
            self.memory = Memory(experience_file=EXPERIENCE_FILE)

            # 3. 上下文管理器
            logger.info("初始化上下文管理器...")
            self.context = ContextManager()

            # 4. 工具注册中心
            logger.info("初始化工具注册中心...")
            self.tools = ToolRegistry()

            # 5. 规划器 (Plan)
            logger.info("初始化规划器 (Plan)...")
            self.planner = Planner(
                llm_client=self.llm_client,
                tools=self.tools,
                context=self.context
            )

            # 6. 执行器 (Do)
            logger.info("初始化执行器 (Do)...")
            self.executor = Executor(
                tools=self.tools,
                memory=self.memory
            )

            # 7. 检查器 (Check)
            logger.info("初始化检查器 (Check)...")
            self.checker = Checker(llm_client=self.llm_client)

            # 8. 改进器 (Act)
            logger.info("初始化改进器 (Act)...")
            self.actor = Actor(
                llm_client=self.llm_client,
                memory=self.memory,
                max_retry=self.max_retry
            )

            # 9. PDCA 循环控制器
            logger.info("初始化 PDCA 循环控制器...")
            self.pdca = PDCALoop(
                planner=self.planner,
                executor=self.executor,
                checker=self.checker,
                actor=self.actor,
                max_pdca_cycles=self.max_cycles
            )

        except Exception as e:
            logger.error(f"组件初始化失败 | error={e}")
            raise

    def run(self, task: str) -> dict:
        """
        运行智能代理执行任务

        Args:
            task: 任务描述

        Returns:
            执行结果字典
        """
        try:
            # 添加任务到上下文
            self.context.add_context(f"用户任务: {task}")

            # 运行 PDCA 循环
            result = self.pdca.run(task)

            # 输出结果摘要
            self._print_summary(result)

            return result

        except Exception as e:
            logger.error(f"任务执行失败 | error={e}")
            return {
                "success": False,
                "error": str(e),
                "summary": f"任务执行出错: {str(e)}"
            }

    def _print_summary(self, result: dict):
        """打印执行结果摘要"""
        logger.info("="*60)
        logger.info("📊 执行结果摘要")
        logger.info("="*60)
        logger.info(f"状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
        logger.info(f"PDCA 循环次数: {result['cycles']}")
        logger.info(f"总步骤数: {len(result.get('final_plan', []))}")
        logger.info(f"摘要: {result['summary']}")
        logger.info("="*60)

    def get_experiences(self, task: str = None, top_k: int = 5):
        """
        获取历史经验

        Args:
            task: 任务描述（用于查找相似经验）
            top_k: 返回数量

        Returns:
            经验列表
        """
        if task:
            return self.actor.get_similar_experiences(task, top_k)
        else:
            all_exp = self.memory.get_all_experiences()
            return all_exp[-top_k:] if len(all_exp) > top_k else all_exp


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python main.py <任务描述>")
        print("示例: python main.py '创建一个Python文件并写入Hello World'")
        sys.exit(1)

    task = " ".join(sys.argv[1:])

    # 创建智能代理
    agent = IntelliAgent()

    # 执行任务
    result = agent.run(task)

    # 返回状态码
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
IntelliAgent - 基于 ReAct 循环的智能代理
主入口文件
"""
import sys
import argparse
from core.llm_client import LLMClient
from core.react_engine import ReactEngine
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
        max_iterations: int = None
    ):
        """
        初始化智能代理

        Args:
            api_key: OpenAI API Key
            model: 使用的模型
            max_iterations: 最大迭代次数
        """
        logger.info("="*60)
        logger.info("🤖 初始化 IntelliAgent 智能代理系统")
        logger.info("="*60)

        # 使用配置或参数
        self.api_key = api_key or OPENAI_API_KEY
        self.model = model or OPENAI_MODEL
        self.max_iterations = max_iterations or MAX_PDCA_CYCLES

        # 初始化各个组件
        self._initialize_components()

        logger.info("✅ 智能代理初始化完成")
        logger.info(f"   模型: {self.model}")
        logger.info(f"   最大迭代次数: {self.max_iterations}")
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

            # 5. ReAct 循环引擎
            logger.info("初始化 ReAct 循环引擎...")
            self.react_engine = ReactEngine(
                llm_client=self.llm_client,
                tools=self.tools,
                memory=self.memory,
                context=self.context,
                max_iterations=self.max_iterations
            )

        except Exception as e:
            logger.error(f"组件初始化失败 | error={e}")
            raise

    def run(self, task: str, max_iterations: int = None) -> dict:
        """
        运行智能代理执行任务

        Args:
            task: 任务描述
            max_iterations: 最大迭代次数（覆盖默认值）

        Returns:
            执行结果字典
        """
        try:
            # 添加任务到上下文
            self.context.add_context(f"用户任务: {task}")

            # 运行 ReAct 循环
            result = self.react_engine.run(task, max_iterations=max_iterations)

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
        logger.info(f"迭代次数: {result.get('iterations', 0)}")
        logger.info(f"摘要: {result.get('summary', '无摘要')}")
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
        # ReAct 模式下暂不支持相似经验查询
        all_exp = self.memory.get_all_experiences()
        return all_exp[-top_k:] if len(all_exp) > top_k else all_exp


def main():
    """命令行入口"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='IntelliAgent - 基于 ReAct 循环的代码开发助手'
    )
    
    parser.add_argument(
        'task',
        type=str,
        nargs='*',
        help='任务描述（例如："创建一个Python文件并编写测试"）'
    )
    
    parser.add_argument(
        '--web',
        action='store_true',
        help='启动 Web UI 服务器'
    )
    
    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='使用的模型（例如：gpt-4o-mini）'
    )
    
    args = parser.parse_args()
    
    # 启动 Web 服务器模式
    if args.web:
        logger.info("="*60)
        logger.info("🌐 启动 Web UI 模式")
        logger.info("="*60)
        
        from web.server import app
        import uvicorn
        
        host = '0.0.0.0'
        port = 8000
        
        logger.info(f"   地址: http://{host}:{port}")
        logger.info(f"   API 文档: http://{host}:{port}/docs")
        logger.info("="*60 + "\n")
        
        uvicorn.run(app, host=host, port=port)
    
    # 命令行模式
    elif not args.task:
        parser.print_help()
        sys.exit(1)
    
    else:
        # 命令行执行模式
        if args.task:
            task = " ".join(args.task)
        else:
            parser.print_help()
            sys.exit(1)
        
        # 创建智能代理
        agent = IntelliAgent(model=args.model)
        
        # 执行任务
        result = agent.run(task)
        
        # 返回状态码
        sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()

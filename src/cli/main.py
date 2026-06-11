#!/usr/bin/env python3
"""
统一 CLI 入口。

PR1 只收敛入口与兼容逻辑；完整子命令能力在 PR5 继续扩展。
"""

from __future__ import annotations

import asyncio
import argparse
import sys
from uuid import uuid4
from typing import Sequence

from src.config import get_settings
from src.runtime import get_runtime
from src.services import RunService, SessionService
from src.db.manager import DatabaseManager, resolve_sqlite_database_path
from utils.logger import logger


class IntelliAgent:
    """智能代理主类。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_iterations: int | None = None,
    ):
        settings = get_settings()

        logger.info("=" * 60)
        logger.info("🤖 初始化 IntelliAgent 智能代理系统")
        logger.info("=" * 60)

        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model = model or settings.OPENAI_MODEL
        self.max_iterations = max_iterations or settings.MAX_PDCA_CYCLES
        self.runtime = get_runtime()
        self.run_service = RunService(self.runtime)
        self.db_manager = DatabaseManager(
            str(resolve_sqlite_database_path(settings.DATABASE_URL))
        )
        self.session_service = SessionService(self.db_manager)

        self._initialize_components()

        logger.info("✅ 智能代理初始化完成")
        logger.info(f"   模型: {self.model}")
        logger.info(f"   最大迭代次数: {self.max_iterations}")
        logger.info("=" * 60 + "\n")

    def _initialize_components(self) -> None:
        """初始化共享运行时。"""
        try:
            self.runtime.warm_up(api_key=self.api_key, model=self.model)
        except Exception as exc:
            logger.error(f"组件初始化失败 | error={exc}")
            raise

    def run(self, task: str, max_iterations: int | None = None) -> dict:
        """同步兼容入口。"""
        return asyncio.run(self.run_async(task, max_iterations=max_iterations))

    async def run_async(self, task: str, max_iterations: int | None = None) -> dict:
        """执行任务。"""
        try:
            await self.db_manager.initialize()
            conversation_id = str(uuid4())
            await self.session_service.create_session(
                session_id=conversation_id,
                title=task[:50] if task else "新任务",
                task=task,
                status="idle",
            )

            result = await self.run_service.run_task_async(
                task=task,
                max_iterations=max_iterations or self.max_iterations,
                api_key=self.api_key,
                model=self.model,
                conversation_id=conversation_id,
            )
            self._print_summary(result)
            return result
        except Exception as exc:
            logger.error(f"任务执行失败 | error={exc}")
            return {
                "success": False,
                "error": str(exc),
                "summary": f"任务执行出错: {exc}",
            }

    def _print_summary(self, result: dict) -> None:
        """打印执行结果摘要。"""
        logger.info("=" * 60)
        logger.info("📊 执行结果摘要")
        logger.info("=" * 60)
        logger.info(f"状态: {'✅ 成功' if result['success'] else '❌ 失败'}")
        logger.info(f"迭代次数: {result.get('iterations', 0)}")
        logger.info(f"摘要: {result.get('summary', '无摘要')}")
        logger.info("=" * 60)

    def get_experiences(self, task: str | None = None, top_k: int = 5):
        """获取历史经验。"""
        all_exp = self.runtime.create_memory().get_all_experiences()
        return all_exp[-top_k:] if len(all_exp) > top_k else all_exp


def normalize_legacy_argv(argv: Sequence[str]) -> list[str]:
    """兼容旧入口参数。

    - `python main.py 任务` -> `run 任务`
    - `python main.py --web` -> `web`
    """
    normalized = list(argv)
    if not normalized or normalized[0] in {"-h", "--help"}:
        return normalized

    if "--web" in normalized:
        web_args = ["web"]
        index = 0
        while index < len(normalized):
            arg = normalized[index]

            if arg == "--web":
                index += 1
                continue

            if arg == "--model":
                index += 2
                continue

            if arg in {"--host", "--port"} and index + 1 < len(normalized):
                web_args.extend([arg, normalized[index + 1]])
                index += 2
                continue

            index += 1

        return web_args

    if normalized[0] in {"run", "web"}:
        return normalized

    return ["run", *normalized]


def build_parser() -> argparse.ArgumentParser:
    """构建统一 CLI 解析器。"""
    parser = argparse.ArgumentParser(
        description="IntelliAgent - 基于 ReAct 循环的代码开发助手"
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="执行一个任务")
    run_parser.add_argument(
        "task",
        nargs="+",
        help="任务描述（例如：创建一个 Python 文件并编写测试）",
    )
    run_parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="使用的模型（例如：gpt-4o-mini）",
    )

    web_parser = subparsers.add_parser("web", help="启动 Web UI 服务器")
    web_parser.add_argument("--host", type=str, default=None, help="监听地址")
    web_parser.add_argument("--port", type=int, default=None, help="监听端口")

    return parser


def run_command(args: argparse.Namespace) -> int:
    """执行 run 子命令。"""
    task = " ".join(args.task)
    agent = IntelliAgent(model=args.model)
    result = agent.run(task)
    return 0 if result["success"] else 1


def web_command(args: argparse.Namespace) -> int:
    """执行 web 子命令。"""
    settings = get_settings()

    import uvicorn

    host = args.host or settings.WEB_HOST
    port = args.port or settings.WEB_PORT

    logger.info("=" * 60)
    logger.info("🌐 启动 Web UI 模式")
    logger.info("=" * 60)
    logger.info(f"   地址: http://{host}:{port}")
    logger.info(f"   API 文档: http://{host}:{port}/docs")
    logger.info("=" * 60 + "\n")

    uvicorn.run("src.app:app", host=host, port=port)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI 主入口。"""
    parser = build_parser()
    normalized_argv = normalize_legacy_argv(argv if argv is not None else sys.argv[1:])

    if not normalized_argv:
        parser.print_help()
        return 1

    args = parser.parse_args(normalized_argv)

    if args.command == "run":
        return run_command(args)
    if args.command == "web":
        return web_command(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

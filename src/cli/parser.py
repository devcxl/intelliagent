#!/usr/bin/env python3
"""CLI 参数解析（纯函数，无副作用）。"""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器（纯函数，无副作用）。"""
    parser = argparse.ArgumentParser(
        description="IntelliAgent — AI 编程助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "读取 pyproject.toml 告诉我项目名"
  %(prog)s --resume "继续刚才的工作"
  %(prog)s --session conv-123456 "新任务"
  %(prog)s --history
        """,
    )
    parser.add_argument("task", nargs="*", help="任务描述")
    parser.add_argument("--resume", "-r", action="store_true", help="继续最近一次 Conversation")
    parser.add_argument("--session", "-s", type=str, help="指定 Conversation ID 继续（兼容参数）")
    parser.add_argument("--history", "-l", action="store_true", help="列出所有历史 Conversation")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数（纯函数，无副作用）。"""
    return build_parser().parse_args(argv)

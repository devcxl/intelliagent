#!/usr/bin/env python3
"""IntelliAgent CLI bootstrap。"""

from __future__ import annotations

import asyncio
import sys

from src.cli.application import CliApplication
from src.cli.parser import build_parser, parse_args


async def main(
    session_id: str | None = None,
    resume: bool = False,
    list_history: bool = False,
) -> None:
    await CliApplication().run(session_id=session_id, resume=resume, list_history=list_history)


if __name__ == "__main__":
    args = parse_args()

    task_text = " ".join(args.task) if args.task else ""
    if task_text and not args.history:
        build_parser().print_help()
        print("\n❌ 多轮对话模式不支持命令行传入任务。请直接运行 python -m src.cli.main 进入交互模式。")
        sys.exit(1)

    asyncio.run(
        main(
            session_id=args.session,
            resume=args.resume,
            list_history=args.history,
        )
    )

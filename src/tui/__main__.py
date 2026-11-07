"""python -m src.tui 免安装入口（README「TUI（交互式）」）。

会话选择（ADR 0013）：缺省新建会话；``-c`` 恢复本目录最近创建的会话；``-s`` 打开指定
会话。运行中可用 ``/resume`` 切换、``/new`` 新建，多开窗口即多会话。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from src.config.yaml_config import ConfigError
from src.core.plugin_host import PluginError
from src.runtime.plugin_assembly import redact_secrets
from src.runtime.session import SessionError
from src.tui.assembly import build_app

EXIT_STARTUP_FAILURE = 2


def build_parser() -> argparse.ArgumentParser:
    """argparse 解析：--config + 会话选择（``-c`` 与 ``-s`` 互斥）。"""
    parser = argparse.ArgumentParser(
        prog="intelliagent-tui",
        description="IntelliAgent 交互式终端界面",
    )
    parser.add_argument("--config", help="intelliagent.yaml 路径（默认当前目录的 intelliagent.yaml）")
    session = parser.add_mutually_exclusive_group()
    session.add_argument("-c", "--continue", dest="resume_last", action="store_true", help="恢复本目录最近创建的会话")
    session.add_argument("-s", "--session", dest="conversation_id", help="打开指定会话 id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """组装并运行 TUI；同步/异步启动错误由入口或应用脱敏后以 2 退出。"""
    args = build_parser().parse_args(argv)
    try:
        app = build_app(
            args.config,
            resume_last=args.resume_last,
            conversation_id=args.conversation_id,
        )
    except (ConfigError, PluginError, SessionError, ValueError) as exc:
        sys.stderr.write(f"error: {redact_secrets(str(exc))}\n")
        return EXIT_STARTUP_FAILURE
    app.run()
    return getattr(app, "return_code", 0)


if __name__ == "__main__":
    raise SystemExit(main())

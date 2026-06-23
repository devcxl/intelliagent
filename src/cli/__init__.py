#!/usr/bin/env python3
"""CLI 模块 — 命令行参数解析、展示。"""

from src.cli.parser import build_parser, parse_args
from src.cli.presenter import (
    format_conversation_header,
    format_event,
    format_history_conversation,
    show_history,
    show_save_info,
)

__all__ = [
    "build_parser",
    "parse_args",
    "format_conversation_header",
    "format_event",
    "format_history_conversation",
    "show_history",
    "show_save_info",
]

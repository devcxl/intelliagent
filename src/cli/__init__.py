#!/usr/bin/env python3
"""CLI 模块 — 命令行参数解析、编排、展示。"""

from src.cli.orchestrator import ConversationOrchestrator
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
    "ConversationOrchestrator",
    "format_conversation_header",
    "format_event",
    "format_history_conversation",
    "show_history",
    "show_save_info",
]

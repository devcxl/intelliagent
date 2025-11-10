#!/usr/bin/env python3
"""
日志工具
提供统一的日志记录功能
"""
import logging
import sys
from typing import Optional


def setup_logger(
    name: str = "intelliagent",
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别
        format_string: 日志格式字符串

    Returns:
        配置好的日志记录器
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 避免重复添加处理器
    if not logger.handlers:
        # 创建控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        # 创建格式化器
        formatter = logging.Formatter(format_string)
        console_handler.setFormatter(formatter)

        # 添加处理器到日志记录器
        logger.addHandler(console_handler)

    return logger


# 创建默认日志记录器
logger = setup_logger()


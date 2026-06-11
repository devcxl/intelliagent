#!/usr/bin/env python3
"""
@deprecated 兼容重导出，请直接使用 src.db.manager。
"""
from src.db.manager import DatabaseManager, resolve_sqlite_database_path  # noqa: F401

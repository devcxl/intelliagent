#!/usr/bin/env python3
"""静态文件配置。"""

from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.config import get_settings
from utils.logger import logger


def _resolve_runtime_dir(configured_path: Optional[str], *fallbacks: Path) -> Path:
    if configured_path:
        configured = Path(configured_path).expanduser()
        return configured if configured.is_absolute() else Path.cwd() / configured

    for fallback in fallbacks:
        if fallback.exists():
            return fallback

    return fallbacks[0]


def _build_frontend_unavailable_page() -> str:
    return """
    <html>
      <head>
        <meta charset=\"utf-8\" />
        <title>IntelliAgent Web</title>
      </head>
      <body style=\"font-family: sans-serif; margin: 40px;\">
        <h1>IntelliAgent Web 入口已可用</h1>
        <p>FastAPI 已启动，但当前未找到可直接托管的前端静态资源。</p>
        <ul>
          <li>开发模式：请进入 <code>frontend/</code> 启动前端开发服务器</li>
          <li>生产模式：请先构建前端并确保 <code>frontend/dist</code> 或 <code>WEB_FRONTEND_DIST</code> 可用</li>
          <li>后端健康检查：<code>/health</code></li>
        </ul>
      </body>
    </html>
    """


def configure_static_files(app: FastAPI) -> tuple[Path, bool]:
    project_root = Path(__file__).resolve().parents[2]
    runtime_settings = get_settings()

    frontend_dist = _resolve_runtime_dir(
        runtime_settings.WEB_FRONTEND_DIST,
        Path.cwd() / "frontend" / "dist",
        Path.cwd() / "web" / "frontend" / "dist",
        project_root / "frontend" / "dist",
        project_root / "web" / "frontend" / "dist",
    )
    static_dir = _resolve_runtime_dir(
        runtime_settings.WEB_STATIC_DIR,
        Path.cwd() / "web" / "static",
        project_root / "web" / "static",
    )
    production_frontend_available = (
        runtime_settings.WEB_ENV == "production" and frontend_dist.exists()
    )

    if production_frontend_available:
        app.mount("/static", StaticFiles(directory=str(frontend_dist)), name="static")
        logger.info(f"静态文件目录（生产）: {frontend_dist}")
    elif runtime_settings.WEB_ENV == "production":
        logger.warning(f"静态文件目录不存在: {frontend_dist}")
    else:
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
            logger.info(f"静态文件目录（开发）: {static_dir}")
        else:
            logger.warning(f"静态文件目录不存在: {static_dir}")

    return frontend_dist, production_frontend_available

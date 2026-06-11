#!/usr/bin/env python3
"""
FastAPI 应用工厂与生命周期管理。
"""
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager

from src.api.v1 import conversations_router, runs_router, ws_runs_router
from src.config import get_settings
from src.db.manager import DatabaseManager, resolve_sqlite_database_path
from src.runtime import get_runtime
from src.services import RunService, SessionService
from src.web.static import configure_static_files, _build_frontend_unavailable_page
from utils.logger import logger


db: Optional[DatabaseManager] = None
session_service: Optional[SessionService] = None
run_service: Optional[RunService] = None
_frontend_dist: Path = Path()
_production_frontend_available: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global db, session_service, run_service

    runtime_settings = get_settings()
    db = DatabaseManager(
        db_path=str(resolve_sqlite_database_path(runtime_settings.DATABASE_URL))
    )
    await db.initialize()
    session_service = SessionService(db)
    run_service = RunService(get_runtime())
    app.state.session_service = session_service
    app.state.run_service = run_service
    logger.info("数据库初始化完成")

    yield

    logger.info("应用关闭")


app = FastAPI(
    title="IntelliAgent - ReAct Agent",
    description="基于 ReAct 循环的代码开发助手",
    version="2.0.0",
    lifespan=lifespan,
)
app.include_router(conversations_router)
app.include_router(runs_router)
app.include_router(ws_runs_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_frontend_dist, _production_frontend_available = configure_static_files(app)


def get_session_service() -> SessionService:
    if session_service is None:
        raise HTTPException(status_code=500, detail="会话服务未初始化")
    return session_service


def get_run_service() -> RunService:
    if run_service is None:
        raise HTTPException(status_code=500, detail="运行服务未初始化")
    return run_service


async def ensure_conversation(task: str, conversation_id: Optional[str]) -> str:
    service = get_session_service()

    if conversation_id:
        session = await service.get_session(conversation_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conversation_id

    import uuid

    new_conversation_id = str(uuid.uuid4())
    title = task[:50] if task else "新任务"
    await service.create_session(
        session_id=new_conversation_id,
        title=title,
        task=task,
        status="idle",
    )
    return new_conversation_id


from src.web.routes import router as legacy_router
app.include_router(legacy_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "intelliagent-web"}


@app.get("/", response_class=HTMLResponse)
async def read_root():
    runtime_settings = get_settings()
    if _production_frontend_available:
        index_path = _frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(_build_frontend_unavailable_page())
    if runtime_settings.WEB_ENV == "production":
        return HTMLResponse(_build_frontend_unavailable_page())
    else:
        from src.web.static import _resolve_runtime_dir
        static_dir = _resolve_runtime_dir(
            runtime_settings.WEB_STATIC_DIR,
            Path.cwd() / "web" / "static",
            Path(__file__).resolve().parents[2] / "web" / "static",
        )
        index_path = static_dir / "index.html"
        if not index_path.exists():
            return HTMLResponse(_build_frontend_unavailable_page())
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()


@app.get("/{full_path:path}")
async def frontend_fallback(full_path: str):
    if not _production_frontend_available:
        raise HTTPException(status_code=404, detail="Not Found")

    reserved_prefixes = {"api", "health", "docs", "redoc", "openapi.json", "ws", "static"}
    first_segment = full_path.split("/", 1)[0]
    if first_segment in reserved_prefixes:
        raise HTTPException(status_code=404, detail="Not Found")

    candidate = _frontend_dist / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)

    index_path = _frontend_dist / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    return HTMLResponse(_build_frontend_unavailable_page())


if __name__ == "__main__":
    import uvicorn

    runtime_settings = get_settings()
    host = runtime_settings.WEB_HOST
    port = runtime_settings.WEB_PORT

    logger.info("=" * 60)
    logger.info("🌐 启动 FastAPI 服务器")
    logger.info(f"   地址: http://{host}:{port}")
    logger.info(f"   API 文档: http://{host}:{port}/docs")
    logger.info("=" * 60)

    uvicorn.run(app, host=host, port=port)

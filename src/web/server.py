#!/usr/bin/env python3
"""
FastAPI 后端服务器
提供 REST API 和 WebSocket 端点
"""
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from src.api.v1 import conversations_router, runs_router, ws_runs_router
from src.config import get_settings
from src.runtime import get_runtime
from src.services import RunService, RunServiceError, SessionService
from utils.logger import logger

from src.db.manager import DatabaseManager, resolve_sqlite_database_path


project_root = Path(__file__).resolve().parents[2]


def _resolve_runtime_dir(configured_path: Optional[str], *fallbacks: Path) -> Path:
    """解析运行时目录，优先显式配置，其次使用候选回退路径。"""
    if configured_path:
        configured = Path(configured_path).expanduser()
        return configured if configured.is_absolute() else Path.cwd() / configured

    for fallback in fallbacks:
        if fallback.exists():
            return fallback

    return fallbacks[0]


def _build_frontend_unavailable_page() -> str:
    """前端静态资源缺失时的占位页。"""
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


class TaskRequest(BaseModel):
    """任务请求模型"""
    task: str
    conversation_id: Optional[str] = None
    max_iterations: int = 10


class TaskResponse(BaseModel):
    """任务响应模型"""
    success: bool
    summary: str
    iterations: int
    conversation_id: Optional[str] = None
    run_id: Optional[str] = None
    answer: Optional[str] = None
    observations: list = []
    error: Optional[str] = None


class RunCancelRequest(BaseModel):
    """取消 run 请求。"""
    run_id: str


class RunRerunRequest(BaseModel):
    """重跑 run 请求。"""
    conversation_id: str
    source_run_id: str
    task: Optional[str] = None
    max_iterations: int = 10


class RunResumeRequest(BaseModel):
    """恢复 run 请求。"""
    run_id: str


class SessionCreate(BaseModel):
    """创建会话请求"""
    title: str
    task: str = ""
    status: str = "idle"


class SessionUpdate(BaseModel):
    """更新会话请求"""
    title: Optional[str] = None
    task: Optional[str] = None
    status: Optional[str] = None
    logs: Optional[List[Dict[str, Any]]] = None


db: Optional[DatabaseManager] = None
session_service: Optional[SessionService] = None
run_service: Optional[RunService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global db, session_service, run_service
    
    # 启动时初始化数据库
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
    
    # 关闭时的清理工作（如果有）
    logger.info("应用关闭")


# 创建 FastAPI 应用（使用 lifespan）
app = FastAPI(
    title="IntelliAgent - ReAct Agent",
    description="基于 ReAct 循环的代码开发助手",
    version="2.0.0",
    lifespan=lifespan
)
app.include_router(conversations_router)
app.include_router(runs_router)
app.include_router(ws_runs_router)

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
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
    # 生产环境：使用构建后的文件
    # 保留 /static 兼容路径，根路径由后置 SPA fallback 负责
    app.mount("/static", StaticFiles(directory=str(frontend_dist)), name="static")
    logger.info(f"静态文件目录（生产）: {frontend_dist}")
elif runtime_settings.WEB_ENV == "production":
    logger.warning(f"静态文件目录不存在: {frontend_dist}")
else:
    # 开发环境：使用旧的静态文件（向后兼容）
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        logger.info(f"静态文件目录（开发）: {static_dir}")
    else:
        logger.warning(f"静态文件目录不存在: {static_dir}")


def get_session_service() -> SessionService:
    """获取会话服务。"""
    if session_service is None:
        raise HTTPException(status_code=500, detail="会话服务未初始化")
    return session_service


def get_run_service() -> RunService:
    """获取任务执行服务。"""
    if run_service is None:
        raise HTTPException(status_code=500, detail="运行服务未初始化")
    return run_service


async def ensure_conversation(task: str, conversation_id: Optional[str]) -> str:
    """确保当前运行绑定到某个 conversation。"""
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


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """返回主页面"""
    runtime_settings = get_settings()
    if production_frontend_available:
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return HTMLResponse(_build_frontend_unavailable_page())
    if runtime_settings.WEB_ENV == "production":
        return HTMLResponse(_build_frontend_unavailable_page())
    else:
        # 开发环境：优先使用兼容静态页；缺失时返回占位说明
        index_path = static_dir / "index.html"

        if not index_path.exists():
            return HTMLResponse(_build_frontend_unavailable_page())

        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()


@app.post("/api/run", response_model=TaskResponse)
async def run_task(request: TaskRequest):
    """执行任务（HTTP 轮询模式）"""
    try:
        logger.info(f"收到任务请求 | task={request.task[:50]}...")
        conversation_id = await ensure_conversation(request.task, request.conversation_id)
        result = await get_run_service().run_task_async(
            task=request.task,
            max_iterations=request.max_iterations,
            conversation_id=conversation_id,
        )
        result["conversation_id"] = conversation_id
        
        logger.info(f"任务执行完成 | success={result['success']}")
        return TaskResponse(**result)
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    
    except Exception as e:
        logger.error(f"任务执行失败 | error={e}")
        import traceback
        logger.debug(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"任务执行失败: {str(e)}")


@app.websocket("/ws/run")
async def websocket_run(websocket: WebSocket):
    """WebSocket 实时推送执行过程"""
    await websocket.accept()
    
    try:
        # 接收任务请求
        data = await websocket.receive_json()
        task = data.get("task", "")
        conversation_id = await ensure_conversation(task, data.get("conversation_id"))
        max_iterations = data.get("max_iterations", 10)
        
        logger.info(f"收到 WebSocket 任务请求 | task={task[:50]}...")
        
        # 发送开始消息
        await websocket.send_json({
            "type": "start",
            "data": {
                "task": task,
                "max_iterations": max_iterations,
                "conversation_id": conversation_id,
            }
        })
        
        # 使用流式执行
        terminal_event_type = None
        terminal_payload = None
        async for step in get_run_service().run_task_stream(
            task=task,
            max_iterations=max_iterations,
            conversation_id=conversation_id,
        ):
            if step["type"] in {"answer", "error", "cancelled", "timeout"}:
                terminal_event_type = step["type"]
                terminal_payload = step
            await websocket.send_json({
                "type": "step",
                "data": step
            })
        
        if terminal_event_type == "answer":
            await websocket.send_json({
                "type": "complete",
                "data": {
                    "status": "completed",
                    "message": "任务执行完成",
                    "conversation_id": conversation_id,
                    "run_id": terminal_payload.get("run_id") if terminal_payload else None,
                }
            })
        elif terminal_event_type in {"error", "timeout"}:
            await websocket.send_json({
                "type": "failed",
                "data": {
                    "status": "failed",
                    "message": terminal_payload.get("message") if terminal_payload else "任务执行失败",
                    "conversation_id": conversation_id,
                    "run_id": terminal_payload.get("run_id") if terminal_payload else None,
                }
            })
        elif terminal_event_type == "cancelled":
            await websocket.send_json({
                "type": "cancelled",
                "data": {
                    "status": "cancelled",
                    "message": terminal_payload.get("message") if terminal_payload else "任务已取消",
                    "conversation_id": conversation_id,
                    "run_id": terminal_payload.get("run_id") if terminal_payload else None,
                }
            })
        
        logger.info("WebSocket 任务执行完成")
    except RunServiceError as exc:
        await websocket.send_json({
            "type": "error",
            "data": {"error": str(exc), "code": exc.code},
        })
    
    except WebSocketDisconnect:
        logger.info("WebSocket 连接已断开")
    except Exception as e:
        logger.error(f"WebSocket 任务执行失败 | error={e}")
        import traceback
        logger.debug(traceback.format_exc())
        
        # 发送错误消息
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"error": str(e)}
            })
        except:
            pass


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "service": "intelliagent-web"}


# ========== 会话管理 API ==========

@app.get("/api/sessions")
async def get_sessions():
    """获取所有会话"""
    sessions = await get_session_service().get_all_sessions()
    return {"sessions": sessions}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """获取指定会话"""
    session = await get_session_service().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return session


@app.post("/api/sessions")
async def create_session(request: SessionCreate):
    """创建新会话"""
    import uuid
    session_id = str(uuid.uuid4())
    
    session = await get_session_service().create_session(
        session_id=session_id,
        title=request.title,
        task=request.task,
        status=request.status
    )
    
    return session


@app.put("/api/sessions/{session_id}")
async def update_session(session_id: str, request: SessionUpdate):
    """更新会话"""
    success = await get_session_service().update_session(
        session_id=session_id,
        title=request.title,
        task=request.task,
        status=request.status,
        logs=request.logs
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    session = await get_session_service().get_session(session_id)
    return session


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    success = await get_session_service().delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    return {"message": "会话已删除"}


@app.post("/api/runs/cancel")
async def cancel_run(request: RunCancelRequest):
    cancelled = await get_run_service().cancel_run(request.run_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Run 不存在或不可取消")
    return {"success": True, "run_id": request.run_id}


@app.post("/api/runs/rerun", response_model=TaskResponse)
async def rerun_task(request: RunRerunRequest):
    session = await get_session_service().get_session(request.conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    task = request.task or session.get("task") or ""
    try:
        result = await get_run_service().rerun(
            conversation_id=request.conversation_id,
            task=task,
            max_iterations=request.max_iterations,
            source_run_id=request.source_run_id,
        )
        result["conversation_id"] = request.conversation_id
        return TaskResponse(**result)
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.post("/api/runs/resume", response_model=TaskResponse)
async def resume_run(request: RunResumeRequest):
    try:
        result = await get_run_service().resume(request.run_id)
        return TaskResponse(**result)
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@app.get("/{full_path:path}")
async def frontend_fallback(full_path: str):
    """生产模式下的 SPA 回退路由。"""
    if not production_frontend_available:
        raise HTTPException(status_code=404, detail="Not Found")

    reserved_prefixes = {"api", "health", "docs", "redoc", "openapi.json", "ws", "static"}
    first_segment = full_path.split("/", 1)[0]
    if first_segment in reserved_prefixes:
        raise HTTPException(status_code=404, detail="Not Found")

    candidate = frontend_dist / full_path
    if candidate.exists() and candidate.is_file():
        return FileResponse(candidate)

    index_path = frontend_dist / "index.html"
    if index_path.exists():
        return FileResponse(index_path)

    return HTMLResponse(_build_frontend_unavailable_page())


if __name__ == "__main__":
    import uvicorn
    
    # 启动服务器
    runtime_settings = get_settings()
    host = runtime_settings.WEB_HOST
    port = runtime_settings.WEB_PORT
    
    logger.info("=" * 60)
    logger.info("🌐 启动 FastAPI 服务器")
    logger.info(f"   地址: http://{host}:{port}")
    logger.info(f"   API 文档: http://{host}:{port}/docs")
    logger.info("=" * 60)
    
    uvicorn.run(app, host=host, port=port)

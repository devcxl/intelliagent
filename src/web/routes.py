#!/usr/bin/env python3
"""
旧 API 端点。

@deprecated 请逐步迁移到 src.api.v1。
"""
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

from src.config import get_settings
from src.services import RunServiceError
from utils.logger import logger


class TaskRequest(BaseModel):
    task: str
    conversation_id: Optional[str] = None
    max_iterations: int = 10


class TaskResponse(BaseModel):
    success: bool
    summary: str
    iterations: int
    conversation_id: Optional[str] = None
    run_id: Optional[str] = None
    answer: Optional[str] = None
    observations: list = []
    error: Optional[str] = None


class RunCancelRequest(BaseModel):
    run_id: str


class RunRerunRequest(BaseModel):
    conversation_id: str
    source_run_id: str
    task: Optional[str] = None
    max_iterations: int = 10


class RunResumeRequest(BaseModel):
    run_id: str


class SessionCreate(BaseModel):
    title: str
    task: str = ""
    status: str = "idle"


class SessionUpdate(BaseModel):
    title: Optional[str] = None
    task: Optional[str] = None
    status: Optional[str] = None
    logs: Optional[List[Dict[str, Any]]] = None


router = APIRouter()


def _get_session_service():
    from src.web.server import get_session_service
    return get_session_service()


def _get_run_service():
    from src.web.server import get_run_service
    return get_run_service()


def _ensure_conversation(task: str, conversation_id: Optional[str]) -> str:
    from src.web.server import ensure_conversation
    import asyncio
    return asyncio.get_event_loop().run_until_complete(
        ensure_conversation(task, conversation_id)
    )


async def _ensure_conversation_async(task: str, conversation_id: Optional[str]) -> str:
    from src.web.server import ensure_conversation
    return await ensure_conversation(task, conversation_id)


@router.post("/api/run", response_model=TaskResponse)
async def run_task(request: TaskRequest):
    try:
        logger.info(f"收到任务请求 | task={request.task[:50]}...")
        conversation_id = await _ensure_conversation_async(request.task, request.conversation_id)
        result = await _get_run_service().run_task_async(
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


@router.websocket("/ws/run")
async def websocket_run(websocket: WebSocket):
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        task = data.get("task", "")
        conversation_id = await _ensure_conversation_async(task, data.get("conversation_id"))
        max_iterations = data.get("max_iterations", 10)

        logger.info(f"收到 WebSocket 任务请求 | task={task[:50]}...")

        await websocket.send_json({
            "type": "start",
            "data": {
                "task": task,
                "max_iterations": max_iterations,
                "conversation_id": conversation_id,
            }
        })

        terminal_event_type = None
        terminal_payload = None
        async for step in _get_run_service().run_task_stream(
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
        try:
            await websocket.send_json({
                "type": "error",
                "data": {"error": str(e)}
            })
        except:
            pass


@router.get("/api/sessions")
async def get_sessions():
    sessions = await _get_session_service().get_all_sessions()
    return {"sessions": sessions}


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    session = await _get_session_service().get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.post("/api/sessions")
async def create_session(request: SessionCreate):
    import uuid
    session_id = str(uuid.uuid4())
    session = await _get_session_service().create_session(
        session_id=session_id,
        title=request.title,
        task=request.task,
        status=request.status
    )
    return session


@router.put("/api/sessions/{session_id}")
async def update_session(session_id: str, request: SessionUpdate):
    success = await _get_session_service().update_session(
        session_id=session_id,
        title=request.title,
        task=request.task,
        status=request.status,
        logs=request.logs
    )
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    session = await _get_session_service().get_session(session_id)
    return session


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    success = await _get_session_service().delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"message": "会话已删除"}


@router.post("/api/runs/cancel")
async def cancel_run(request: RunCancelRequest):
    cancelled = await _get_run_service().cancel_run(request.run_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Run 不存在或不可取消")
    return {"success": True, "run_id": request.run_id}


@router.post("/api/runs/rerun", response_model=TaskResponse)
async def rerun_task(request: RunRerunRequest):
    session = await _get_session_service().get_session(request.conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    task = request.task or session.get("task") or ""
    try:
        result = await _get_run_service().rerun(
            conversation_id=request.conversation_id,
            task=task,
            max_iterations=request.max_iterations,
            source_run_id=request.source_run_id,
        )
        result["conversation_id"] = request.conversation_id
        return TaskResponse(**result)
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/api/runs/resume", response_model=TaskResponse)
async def resume_run(request: RunResumeRequest):
    try:
        result = await _get_run_service().resume(request.run_id)
        return TaskResponse(**result)
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

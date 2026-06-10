#!/usr/bin/env python3
"""v1 runs API。"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.api.deps import ensure_conversation, get_run_service, get_session_service
from src.services import RunServiceError


router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


class CreateRunRequest(BaseModel):
    task: str
    conversation_id: Optional[str] = None
    max_iterations: int = 10


class RerunRunRequest(BaseModel):
    conversation_id: str
    source_run_id: str
    task: Optional[str] = None
    max_iterations: int = 10


def _serialize_run(run):
    return {
        "id": run.id,
        "conversation_id": run.conversation_id,
        "task_snapshot": run.task_snapshot,
        "status": run.status,
        "max_iterations": run.max_iterations,
        "current_iteration": run.current_iteration,
        "cancel_requested": run.cancel_requested,
        "source_run_id": run.source_run_id,
        "error": run.error,
        "createdAt": run.created_at.isoformat(),
        "updatedAt": run.updated_at.isoformat(),
    }


def _serialize_trace(trace):
    return {
        "id": trace.id,
        "run_id": trace.run_id,
        "iteration": trace.iteration,
        "type": trace.type,
        "data": json.loads(trace.data),
        "createdAt": trace.created_at.isoformat(),
    }


@router.post("")
async def create_run(
    payload: CreateRunRequest,
    request: Request,
    run_service=Depends(get_run_service),
):
    try:
        conversation_id = await ensure_conversation(
            request.app,
            payload.task,
            payload.conversation_id,
        )
        result = await run_service.run_task_async(
            task=payload.task,
            max_iterations=payload.max_iterations,
            conversation_id=conversation_id,
        )
        result["conversation_id"] = conversation_id
        return result
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    run_service=Depends(get_run_service),
):
    run = await run_service.run_repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    return _serialize_run(run)


@router.get("/{run_id}/traces")
async def list_run_traces(
    run_id: str,
    run_service=Depends(get_run_service),
):
    run = await run_service.run_repository.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run 不存在")
    traces = await run_service.trace_repository.list_by_run(run_id)
    return {"traces": [_serialize_trace(trace) for trace in traces]}


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    run_service=Depends(get_run_service),
):
    cancelled = await run_service.cancel_run(run_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Run 不存在或不可取消")
    return {"success": True, "run_id": run_id}


@router.post("/rerun")
async def rerun_run(
    payload: RerunRunRequest,
    session_service=Depends(get_session_service),
    run_service=Depends(get_run_service),
):
    session = await session_service.get_session(payload.conversation_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    task = payload.task or session.get("task") or ""
    try:
        result = await run_service.rerun(
            conversation_id=payload.conversation_id,
            task=task,
            max_iterations=payload.max_iterations,
            source_run_id=payload.source_run_id,
        )
        result["conversation_id"] = payload.conversation_id
        return result
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/{run_id}/resume")
async def resume_run(
    run_id: str,
    run_service=Depends(get_run_service),
):
    try:
        return await run_service.resume(run_id)
    except RunServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

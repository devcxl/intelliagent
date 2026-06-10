#!/usr/bin/env python3
"""v1 conversations API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.deps import get_run_service, get_session_service


router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


def _serialize_message(message):
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "createdAt": message.created_at.isoformat(),
    }


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


@router.get("")
async def list_conversations(
    request: Request,
    session_service=Depends(get_session_service),
):
    conversations = await session_service.get_all_sessions()
    return {"conversations": conversations}


@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    request: Request,
    session_service=Depends(get_session_service),
):
    conversation = await session_service.get_session(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conversation


@router.get("/{conversation_id}/messages")
async def list_conversation_messages(
    conversation_id: str,
    request: Request,
    session_service=Depends(get_session_service),
    run_service=Depends(get_run_service),
):
    conversation = await session_service.get_session(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = await run_service.message_repository.list_by_conversation(conversation_id)
    return {"messages": [_serialize_message(message) for message in messages]}


@router.get("/{conversation_id}/runs")
async def list_conversation_runs(
    conversation_id: str,
    request: Request,
    session_service=Depends(get_session_service),
    run_service=Depends(get_run_service),
):
    conversation = await session_service.get_session(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    runs = await run_service.run_repository.list_by_conversation(conversation_id)
    return {"runs": [_serialize_run(run) for run in runs]}

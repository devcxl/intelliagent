#!/usr/bin/env python3
"""API 依赖与共享辅助函数。"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import HTTPException, Request
from starlette.websockets import WebSocket


def _get_state_service(app, name: str, error_message: str):
    service = getattr(app.state, name, None)
    if service is None:
        raise HTTPException(status_code=500, detail=error_message)
    return service


def get_session_service(request: Request):
    return _get_state_service(request.app, "session_service", "会话服务未初始化")


def get_run_service(request: Request):
    return _get_state_service(request.app, "run_service", "运行服务未初始化")


def get_session_service_from_websocket(websocket: WebSocket):
    return _get_state_service(websocket.app, "session_service", "会话服务未初始化")


def get_run_service_from_websocket(websocket: WebSocket):
    return _get_state_service(websocket.app, "run_service", "运行服务未初始化")


async def ensure_conversation(app, task: str, conversation_id: Optional[str]) -> str:
    """确保运行绑定到某个 conversation。"""
    service = _get_state_service(app, "session_service", "会话服务未初始化")

    if conversation_id:
        session = await service.get_session(conversation_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conversation_id

    new_conversation_id = str(uuid4())
    title = task[:50] if task else "新任务"
    await service.create_session(
        session_id=new_conversation_id,
        title=title,
        task=task,
        status="idle",
    )
    return new_conversation_id

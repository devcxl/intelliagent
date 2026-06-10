#!/usr/bin/env python3
"""v1 WebSocket runs API。"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.api.deps import ensure_conversation, get_run_service_from_websocket
from src.services import RunServiceError


router = APIRouter(tags=["ws-runs"])


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


@router.websocket("/api/v1/ws/runs")
async def websocket_runs(websocket: WebSocket):
    await websocket.accept()

    try:
        payload = await websocket.receive_json()
        task = payload.get("task", "")
        max_iterations = payload.get("max_iterations", 10)
        conversation_id = await ensure_conversation(
            websocket.app,
            task,
            payload.get("conversation_id"),
        )

        start_sent = False
        terminal_type = None
        terminal_payload = None

        async for event in get_run_service_from_websocket(websocket).run_task_stream(
            task=task,
            max_iterations=max_iterations,
            conversation_id=conversation_id,
        ):
            run_id = event.get("run_id")
            if not start_sent:
                await websocket.send_json(
                    {
                        "type": "start",
                        "data": {
                            "task": task,
                            "max_iterations": max_iterations,
                            "conversation_id": conversation_id,
                            "run_id": run_id,
                            "timestamp": _timestamp(),
                        },
                    }
                )
                start_sent = True

            enriched_event = {
                **event,
                "conversation_id": conversation_id,
                "timestamp": _timestamp(),
            }

            if event["type"] in {"answer", "error", "cancelled", "timeout"}:
                terminal_type = event["type"]
                terminal_payload = enriched_event

            await websocket.send_json({"type": "step", "data": enriched_event})

        if terminal_type == "answer":
            await websocket.send_json(
                {
                    "type": "complete",
                    "data": {
                        "status": "completed",
                        "conversation_id": conversation_id,
                        "run_id": terminal_payload.get("run_id") if terminal_payload else None,
                        "timestamp": _timestamp(),
                    },
                }
            )
        elif terminal_type in {"error", "timeout"}:
            await websocket.send_json(
                {
                    "type": "failed",
                    "data": {
                        "status": "failed",
                        "conversation_id": conversation_id,
                        "run_id": terminal_payload.get("run_id") if terminal_payload else None,
                        "message": terminal_payload.get("message") if terminal_payload else "任务执行失败",
                        "timestamp": _timestamp(),
                    },
                }
            )
        elif terminal_type == "cancelled":
            await websocket.send_json(
                {
                    "type": "cancelled",
                    "data": {
                        "status": "cancelled",
                        "conversation_id": conversation_id,
                        "run_id": terminal_payload.get("run_id") if terminal_payload else None,
                        "message": terminal_payload.get("message") if terminal_payload else "任务已取消",
                        "timestamp": _timestamp(),
                    },
                }
            )
    except RunServiceError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "data": {"error": str(exc), "code": exc.code, "timestamp": _timestamp()},
            }
        )
    except WebSocketDisconnect:
        pass

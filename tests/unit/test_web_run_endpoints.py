#!/usr/bin/env python3
"""Web run 入口测试。"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

import src.web.server as server


class FakeSessionService:
    def __init__(self):
        self.sessions = {}

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def create_session(self, *, session_id, title, task="", status="idle"):
        session = {
            "id": session_id,
            "title": title,
            "task": task,
            "status": status,
            "logs": [],
            "createdAt": "now",
            "updatedAt": "now",
        }
        self.sessions[session_id] = session
        return session


class FakeRunService:
    def __init__(self):
        self.run_payload = None
        self.cancelled_run_id = None

    async def run_task_async(self, **kwargs):
        self.run_payload = kwargs
        return {
            "success": True,
            "summary": "ok",
            "iterations": 1,
            "answer": "done",
            "observations": [],
            "error": None,
            "run_id": "run-1",
        }

    async def run_task_stream(self, **kwargs):
        yield {
            "type": "error",
            "iteration": 1,
            "message": "boom",
            "run_id": "run-ws-1",
        }

    async def cancel_run(self, run_id):
        self.cancelled_run_id = run_id
        return True

    async def rerun(self, **kwargs):
        return {
            "success": True,
            "summary": "rerun-ok",
            "iterations": 1,
            "answer": "rerun",
            "observations": [],
            "error": None,
            "run_id": "run-rerun-1",
            "conversation_id": kwargs["conversation_id"],
        }

    async def resume(self, run_id):
        return {
            "success": True,
            "summary": "resume-ok",
            "iterations": 2,
            "answer": "resume",
            "observations": [],
            "error": None,
            "run_id": run_id,
            "conversation_id": "conversation-resume-1",
        }

        
class FakeRunRepository:
    async def get(self, run_id):
        class Run:
            id = run_id
            conversation_id = "conversation-v1"
            task_snapshot = "测试任务"
            status = "completed"
            max_iterations = 3
            current_iteration = 1
            cancel_requested = False
            source_run_id = None
            error = None
            created_at = datetime.now(UTC)
            updated_at = datetime.now(UTC)

        return Run()

    async def list_by_conversation(self, conversation_id):
        return []


class FakeTraceRepository:
    async def list_by_run(self, run_id):
        return []


class FakeMessageRepository:
    async def list_by_conversation(self, conversation_id):
        return []


def test_http_run_endpoint_routes_to_persisted_branch(monkeypatch):
    fake_session_service = FakeSessionService()
    fake_run_service = FakeRunService()

    monkeypatch.setattr(server, "get_session_service", lambda: fake_session_service)
    monkeypatch.setattr(server, "get_run_service", lambda: fake_run_service)

    with TestClient(server.app) as client:
        response = client.post("/api/run", json={"task": "测试任务", "max_iterations": 3})

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "run-1"
    assert data["conversation_id"] is not None
    assert fake_run_service.run_payload["conversation_id"] == data["conversation_id"]


def test_cancel_run_endpoint_is_callable(monkeypatch):
    fake_run_service = FakeRunService()

    monkeypatch.setattr(server, "get_run_service", lambda: fake_run_service)

    with TestClient(server.app) as client:
        response = client.post("/api/runs/cancel", json={"run_id": "run-123"})

    assert response.status_code == 200
    assert fake_run_service.cancelled_run_id == "run-123"


def test_websocket_error_does_not_emit_complete(monkeypatch):
    fake_session_service = FakeSessionService()
    fake_run_service = FakeRunService()

    monkeypatch.setattr(server, "get_session_service", lambda: fake_session_service)
    monkeypatch.setattr(server, "get_run_service", lambda: fake_run_service)

    with TestClient(server.app) as client:
        with client.websocket_connect("/ws/run") as websocket:
            websocket.send_json({"task": "测试任务", "max_iterations": 3})
            messages = [websocket.receive_json(), websocket.receive_json(), websocket.receive_json()]

    assert messages[0]["type"] == "start"
    assert messages[1]["type"] == "step"
    assert messages[1]["data"]["type"] == "error"
    assert messages[2]["type"] == "failed"


def test_v1_runs_endpoint_returns_conversation_and_run_id():
    fake_session_service = FakeSessionService()
    fake_run_service = FakeRunService()
    fake_run_service.run_repository = FakeRunRepository()
    fake_run_service.trace_repository = FakeTraceRepository()
    fake_run_service.message_repository = FakeMessageRepository()

    with TestClient(server.app) as client:
        server.app.state.session_service = fake_session_service
        server.app.state.run_service = fake_run_service
        response = client.post("/api/v1/runs", json={"task": "测试任务", "max_iterations": 3})

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "run-1"
    assert data["conversation_id"] is not None


def test_v1_websocket_start_contains_run_id_and_timestamp():
    fake_session_service = FakeSessionService()
    fake_run_service = FakeRunService()
    fake_run_service.run_repository = FakeRunRepository()
    fake_run_service.trace_repository = FakeTraceRepository()
    fake_run_service.message_repository = FakeMessageRepository()

    with TestClient(server.app) as client:
        server.app.state.session_service = fake_session_service
        server.app.state.run_service = fake_run_service
        with client.websocket_connect("/api/v1/ws/runs") as websocket:
            websocket.send_json({"task": "测试任务", "max_iterations": 3})
            start = websocket.receive_json()

    assert start["type"] == "start"
    assert start["data"]["run_id"] == "run-ws-1"
    assert start["data"]["conversation_id"] is not None
    assert start["data"]["timestamp"]


def test_resume_endpoint_returns_conversation_id(monkeypatch):
    fake_run_service = FakeRunService()

    monkeypatch.setattr(server, "get_run_service", lambda: fake_run_service)

    with TestClient(server.app) as client:
        response = client.post("/api/runs/resume", json={"run_id": "run-123"})

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == "run-123"
    assert data["conversation_id"] == "conversation-resume-1"

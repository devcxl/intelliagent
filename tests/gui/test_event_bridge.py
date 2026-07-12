"""EventBridge 单元测试 — async → Qt signal 桥接。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.gui.services.event_bridge import EventBridge


class FakeRuntime:
    def __init__(self, events: list[dict[str, Any]] | None = None):
        self._events = events or []
        self._session_id: str | None = None

    @property
    def conversation_id(self):
        return self._session_id

    def switch_session(self, cid: str):
        self._session_id = cid

    async def execute(self, task: str):
        for ev in self._events:
            yield ev


def create_runtime_with_events(*events: dict[str, Any]):
    return FakeRuntime(list(events))


class TestEventBridgeInstantiation:
    def test_create_with_fake_runtime(self):
        runtime = FakeRuntime()
        bridge = EventBridge(runtime)  # type: ignore[arg-type]
        assert bridge is not None

    def test_create_with_real_signals(self):
        runtime = FakeRuntime()
        bridge = EventBridge(runtime)  # type: ignore[arg-type]
        assert hasattr(bridge, "event_received")
        assert hasattr(bridge, "engine_started")
        assert hasattr(bridge, "engine_finished")
        assert hasattr(bridge, "error_occurred")


class TestEventBridgeSignalEmission:
    @pytest.mark.asyncio
    async def test_submit_task_emits_started_and_finished(self):
        events = [{"type": "answer", "data": {"answer": "hi"}}]
        runtime = create_runtime_with_events(*events)
        bridge = EventBridge(runtime)  # type: ignore[arg-type]

        started_called = False
        finished_called = False

        def on_started():
            nonlocal started_called
            started_called = True

        def on_finished(result):
            nonlocal finished_called
            finished_called = True
            assert result.get("success") is True

        bridge.engine_started.connect(on_started)
        bridge.engine_finished.connect(on_finished)

        await bridge.submit_task("hello")

        assert started_called
        assert finished_called

    @pytest.mark.asyncio
    async def test_submit_task_emits_events_in_order(self):
        events = [
            {"type": "thought", "data": {"content": "thinking..."}},
            {"type": "answer", "data": {"answer": "done"}},
        ]
        runtime = create_runtime_with_events(*events)
        bridge = EventBridge(runtime)  # type: ignore[arg-type]

        received: list[dict] = []

        def on_event(event):
            received.append(event)

        bridge.event_received.connect(on_event)

        await bridge.submit_task("do it")

        assert len(received) == 2
        assert received[0]["type"] == "thought"
        assert received[1]["type"] == "answer"

    @pytest.mark.asyncio
    async def test_submit_task_error_emits_error_signal(self):
        runtime = MagicMock()

        async def broken_execute(task):
            raise RuntimeError("engine crash")
            yield  # type: ignore[unreachable]

        runtime.execute = broken_execute
        bridge = EventBridge(runtime)  # type: ignore[arg-type]

        errors: list[str] = []

        def on_error(msg):
            errors.append(msg)

        bridge.error_occurred.connect(on_error)

        await bridge.submit_task("will fail")

        assert len(errors) == 1
        assert "engine crash" in errors[0]


class TestEventBridgeSessionResume:
    def test_resume_session_sets_pending(self):
        runtime = FakeRuntime()
        bridge = EventBridge(runtime)  # type: ignore[arg-type]

        bridge.resume_session("conv-123")

        assert bridge._pending_session_id == "conv-123"

    def test_resume_same_session_skips_switch(self):
        runtime = FakeRuntime()
        runtime.switch_session("already-here")
        bridge = EventBridge(runtime)  # type: ignore[arg-type]

        bridge.resume_session("already-here")

        # pending should still be set, will be checked in _switch_session_if_needed
        assert bridge._pending_session_id == "already-here"

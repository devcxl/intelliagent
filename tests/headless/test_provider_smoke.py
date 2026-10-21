"""Provider 端到端冒烟：真实 HTTP + OpenAI Compatible 适配器 + 引擎（本地 mock 端点，不触外网）。"""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.headless.cli import main


class _MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 — http.server 接口
        length = int(self.headers.get("content-length", 0))
        self.rfile.read(length)
        chunk = {
            "id": "x",
            "object": "chat.completion.chunk",
            "created": 1,
            "model": "mock-model",
            "choices": [{"index": 0, "delta": {"content": "hello from mock"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        }
        body = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(body)))
        self.send_header("connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def mock_endpoint() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_headless_run_against_local_openai_compatible_endpoint(tmp_path: Path, mock_endpoint: str) -> None:
    config = tmp_path / "intelliagent.yaml"
    config.write_text(
        "default_model: local/mock-model\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        f"    api: {mock_endpoint}\n"
        "    models:\n"
        "      mock-model: {}\n",
        encoding="utf-8",
    )
    stdout, stderr = io.StringIO(), io.StringIO()

    code = main(
        ["run", "hi", "--config", str(config)],
        stdout=stdout,
        stderr=stderr,
        abort=threading.Event(),
    )

    assert code == 0, stderr.getvalue()
    events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith("{")]
    assert any(event["type"] == "message_update" for event in events)
    assert events[-1]["type"] == "agent_end" and events[-1]["outcome"] == "settled"


class _ToolHandler(BaseHTTPRequestHandler):
    """第一次请求返回 read 工具调用，第二次返回最终文本，用于验证工具调用流式链路。"""

    protocol_version = "HTTP/1.1"
    requests = 0

    def do_POST(self) -> None:  # noqa: N802 — http.server 接口
        length = int(self.headers.get("content-length", 0))
        self.rfile.read(length)
        type(self).requests += 1
        if type(self).requests == 1:
            chunk = {
                "id": "x",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "mock-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "read", "arguments": '{"path": "README.md"}'},
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
            }
        else:
            chunk = {
                "id": "y",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "mock-model",
                "choices": [{"index": 0, "delta": {"content": "done"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            }
        body = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(body)))
        self.send_header("connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def mock_tool_endpoint() -> str:
    _ToolHandler.requests = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ToolHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_headless_tool_call_streaming_against_local_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mock_tool_endpoint: str
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# IntelliAgent\n", encoding="utf-8")
    config = tmp_path / "intelliagent.yaml"
    config.write_text(
        "default_model: local/mock-model\n"
        "providers:\n"
        "  local:\n"
        "    type: openai-compatible\n"
        f"    api: {mock_tool_endpoint}\n"
        "    models:\n"
        "      mock-model: {}\n",
        encoding="utf-8",
    )
    stdout, stderr = io.StringIO(), io.StringIO()

    code = main(
        ["run", "read README", "--config", str(config)],
        stdout=stdout,
        stderr=stderr,
        abort=threading.Event(),
    )

    assert code == 0, stderr.getvalue()
    events = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith("{")]
    kinds = [event["type"] for event in events]
    assert "tool_execution_start" in kinds
    assert "tool_execution_end" in kinds
    assert events[-1]["type"] == "agent_end" and events[-1]["outcome"] == "settled"

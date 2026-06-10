#!/usr/bin/env python3
"""PR1 入口与兼容性测试。"""

from src.app import app
from src.cli.main import build_parser, main, normalize_legacy_argv


def test_web_entrypoint_importable():
    assert app.title == "IntelliAgent - ReAct Agent"


def test_cli_entrypoint_importable():
    assert callable(main)


def test_cli_parser_supports_run_command():
    parser = build_parser()
    args = parser.parse_args(["run", "测试任务"])

    assert args.command == "run"
    assert args.task == ["测试任务"]


def test_legacy_task_arguments_are_normalized():
    assert normalize_legacy_argv(["修复测试"]) == ["run", "修复测试"]
    assert normalize_legacy_argv(["--web"]) == ["web"]
    assert normalize_legacy_argv(["--web", "旧任务参数"]) == ["web"]
    assert normalize_legacy_argv(["--web", "--model", "gpt-4o-mini"]) == ["web"]
    assert normalize_legacy_argv(["--web", "--host", "127.0.0.1", "--port", "9000"]) == [
        "web",
        "--host",
        "127.0.0.1",
        "--port",
        "9000",
    ]


def test_api_routes_are_registered_before_frontend_fallback():
    route_paths = [route.path for route in app.routes]

    assert "/health" in route_paths
    assert "/api/sessions" in route_paths
    assert "/{full_path:path}" in route_paths
    assert route_paths.index("/health") < route_paths.index("/{full_path:path}")
    assert route_paths.index("/api/sessions") < route_paths.index("/{full_path:path}")

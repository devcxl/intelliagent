"""CommandParser 单元测试 — 斜杠命令解析与分发。"""

from __future__ import annotations

from src.gui.services.command_parser import CommandParser


def test_parse_normal_text_returns_not_handled():
    parser = CommandParser()
    handled, result = parser.parse("你好")
    assert handled is False
    assert result is None


def test_parse_slash_triggers_handler():
    called_args: list[str] = []

    def handler(args: str) -> str:
        called_args.append(args)
        return "ok"

    parser = CommandParser()
    parser.register("/new", handler)
    handled, result = parser.parse("/new hello world")
    assert handled is True
    assert result == "ok"
    assert called_args == ["hello world"]


def test_parse_unknown_command_returns_error():
    parser = CommandParser()
    handled, result = parser.parse("/unknown")
    assert handled is True
    assert result is not None
    assert "未知命令" in str(result)


def test_parse_command_without_args_returns_empty_args():
    called_args: list[str] = []

    def handler(args: str) -> str:
        called_args.append(args)
        return ""

    parser = CommandParser()
    parser.register("/delete", handler)
    handled, result = parser.parse("/delete")
    assert handled is True
    assert called_args == [""]


def test_parse_empty_string():
    parser = CommandParser()
    handled, result = parser.parse("")
    assert handled is False
    assert result is None


def test_multiple_commands_registered():
    parser = CommandParser()
    results: list[str] = []

    def make_handler(name: str):
        def h(args: str) -> str:
            results.append(f"{name}:{args}")
            return f"ok-{name}"

        return h

    parser.register("/new", make_handler("new"))
    parser.register("/delete", make_handler("delete"))
    parser.register("/resume", make_handler("resume"))

    h1, r1 = parser.parse("/delete session-1")
    h2, r2 = parser.parse("/resume abc-123")

    assert h1 is True
    assert r1 == "ok-delete"
    assert h2 is True
    assert r2 == "ok-resume"
    assert results == ["delete:session-1", "resume:abc-123"]

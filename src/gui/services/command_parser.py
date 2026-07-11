"""斜杠命令解析器 — 注册与分发 /commands。"""

from typing import Callable


class CommandParser:
    """Parser and dispatcher for slash commands.

    Usage::

        parser = CommandParser()
        parser.register("/help", lambda _: "可用命令: /help, /new")
        handled, result = parser.parse("/help")
        assert handled is True
    """

    def __init__(self) -> None:
        self.handlers: dict[str, Callable[[str], str]] = {}

    def register(self, command: str, handler: Callable[[str], str]) -> None:
        """Register a handler for a slash command.

        Args:
            command: Command name including the slash, e.g. ``"/new"``.
            handler: A callable that takes the remaining args string and returns
                a response string.
        """
        self.handlers[command] = handler

    def parse(self, text: str) -> tuple[bool, str | None]:
        """Parse and dispatch a slash command.

        Args:
            text: The raw user input line.

        Returns:
            A tuple ``(handled, result)`` where:
            - ``handled`` is ``True`` if the text starts with ``/``.
            - ``result`` is the handler's response if a matching handler was found,
              an error message if the command is unknown, or ``None`` if the text
              is not a command.
        """
        if not text.startswith("/"):
            return False, None

        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = self.handlers.get(cmd)
        if handler is not None:
            return True, handler(args)

        return True, f"未知命令: {cmd}。输入 /help 查看可用命令。"

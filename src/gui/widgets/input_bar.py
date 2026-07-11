"""输入栏 — 文本输入 + 命令解析 + 发送按钮。"""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QWidget,
)

from src.gui.services.command_parser import CommandParser


class InputBar(QWidget):
    """Bottom input bar with a text field and send button.

    Emits ``submitted(str)`` when the user presses Enter or clicks Send,
    unless the input starts with ``/`` (slash command), in which case the
    command is parsed internally and no signal is emitted.

    Usage::

        parser = CommandParser()
        bar = InputBar(parser)
        bar.submitted.connect(on_user_message)
        bar.setEnabled(False)  # while engine is running
    """

    submitted = pyqtSignal(str)

    def __init__(self, command_parser: CommandParser, parent=None) -> None:
        super().__init__(parent)
        self._parser = command_parser

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText("输入消息...（/help 查看命令）")
        self._input.returnPressed.connect(self._on_submit)
        layout.addWidget(self._input)

        self._send_btn = QPushButton("发送")
        self._send_btn.clicked.connect(self._on_submit)
        layout.addWidget(self._send_btn)

    def setEnabled(self, enabled: bool) -> None:
        """Enable or disable the input controls.

        Useful to block user input while the engine is processing a task.
        """
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    def _on_submit(self) -> None:
        text = self._input.text().strip()
        if not text:
            return

        handled, _ = self._parser.parse(text)
        if handled:
            self._input.clear()
            return

        self.submitted.emit(text)
        self._input.clear()

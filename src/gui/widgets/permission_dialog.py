"""PermissionDialog — 模态权限确认对话框。

实现 PermissionCallbackProtocol，供 PermissionEngine 在 ask 决策时调用。
"""

from __future__ import annotations

import json
from typing import Any

from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class PermissionDialog(QDialog):
    """模态权限确认对话框。

    显示工具名、参数信息及风险原因，用户点击「允许」或「拒绝」后关闭。
    模态阻塞期间无法操作主窗口。
    """

    def __init__(self, tool_name: str, args: dict[str, Any], reason: str) -> None:
        super().__init__()
        self.setWindowTitle("权限确认")
        self.setObjectName("permDialog")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._build_ui(tool_name, args, reason)

    def _build_ui(self, tool_name: str, args: dict[str, Any], reason: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Warning header
        header = QLabel('<span style="font-size: 20px;">⚠️</span> <b>权限请求</b> — 此操作需要您的确认')
        header.setObjectName("permHeader")
        layout.addWidget(header)

        # Tool name
        title_label = QLabel(f"<b>工具</b>：{tool_name}")
        title_label.setObjectName("permTitle")
        layout.addWidget(title_label)

        # Reason
        reason_label = QLabel(f"<b>原因</b>：{reason}")
        reason_label.setObjectName("permReason")
        reason_label.setWordWrap(True)
        layout.addWidget(reason_label)

        # Args preview
        args_text = json.dumps(args, indent=2, ensure_ascii=False)
        args_label = QLabel("<b>参数</b>：")
        args_label.setObjectName("permArgsLabel")
        layout.addWidget(args_label)

        args_edit = QTextEdit()
        args_edit.setObjectName("permArgs")
        args_edit.setPlainText(args_text)
        args_edit.setReadOnly(True)
        args_edit.setMaximumHeight(200)
        layout.addWidget(args_edit)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        deny_btn = QPushButton("拒绝执行")
        deny_btn.setObjectName("permDeny")
        deny_btn.setToolTip("拒绝本次操作，通知 LLM 用户已取消")
        deny_btn.clicked.connect(lambda: self.done(QDialog.Rejected))

        allow_btn = QPushButton("允许执行")
        allow_btn.setObjectName("permAllow")
        allow_btn.setDefault(True)
        allow_btn.setToolTip("允许本次操作继续执行")
        allow_btn.clicked.connect(lambda: self.done(QDialog.Accepted))

        btn_layout.addWidget(deny_btn)
        btn_layout.addWidget(allow_btn)
        layout.addLayout(btn_layout)

    @classmethod
    async def on_prompt(cls, tool_name: str, args: dict[str, Any], reason: str) -> bool:
        """实现 PermissionCallbackProtocol。

        创建并模态显示权限对话框，阻塞直至用户操作。

        Args:
            tool_name: 请求执行的工具名称
            args: 工具参数字典
            reason: 权限引擎给出的决策原因

        Returns:
            用户允许返回 True，拒绝返回 False
        """
        dialog = cls(tool_name, args, reason)
        dialog.exec()
        return dialog.result() == QDialog.Accepted

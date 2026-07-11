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
        self.setModal(True)
        self.setMinimumWidth(480)
        self._build_ui(tool_name, args, reason)

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self, tool_name: str, args: dict[str, Any], reason: str) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 工具名
        title_label = QLabel(f"<b>工具</b>：{tool_name}")
        title_label.setObjectName("permTitle")
        layout.addWidget(title_label)

        reason_label = QLabel(f"<b>原因</b>：{reason}")
        reason_label.setObjectName("permTitle")
        layout.addWidget(reason_label)

        # 参数信息（等宽字体 JSON 预览）
        args_text = json.dumps(args, indent=2, ensure_ascii=False)
        args_edit = QTextEdit()
        args_edit.setPlainText(args_text)
        args_edit.setReadOnly(True)
        args_edit.setMaximumHeight(200)
        args_edit.setStyleSheet("font-family: monospace;")
        layout.addWidget(QLabel("<b>参数</b>："))
        layout.addWidget(args_edit)

        # 按钮栏
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        deny_btn = QPushButton("拒绝")
        deny_btn.setObjectName("permDeny")
        deny_btn.clicked.connect(lambda: self.done(QDialog.Rejected))

        allow_btn = QPushButton("允许")
        allow_btn.setObjectName("permAllow")
        allow_btn.setDefault(True)
        allow_btn.clicked.connect(lambda: self.done(QDialog.Accepted))

        btn_layout.addWidget(deny_btn)
        btn_layout.addWidget(allow_btn)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # PermissionCallbackProtocol 实现
    # ------------------------------------------------------------------

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

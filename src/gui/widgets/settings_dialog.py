"""SettingsDialog — 可编辑的配置面板。"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.config.unified_config import UnifiedConfig


class SettingsDialog(QDialog):
    """设置对话框 — 可编辑的配置表单。"""

    CONFIG_PATH = Path("intelliagent.json")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setObjectName("settingsDialog")
        self.setMinimumSize(600, 480)

        self._config = UnifiedConfig.load()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "通用")
        tabs.addTab(self._build_model_tab(), "模型")
        tabs.addTab(self._build_about_tab(), "关于")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 12)
        btn_row.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setObjectName("settingsSaveBtn")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        close_btn = QPushButton("关闭")
        close_btn.setObjectName("settingsCloseBtn")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    # ── General Tab ──────────────────────────────────────────

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(self._section("Agent"))

        self._agent_id = self._add_field(layout, "Agent ID", self._config.agent_id)

        layout.addWidget(self._section("工作区"))

        workspace_row = QHBoxLayout()
        self._workspace_dir = QLineEdit(self._config.workspace.dir)
        self._workspace_dir.setObjectName("settingsInput")
        workspace_row.addWidget(self._workspace_dir)
        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("settingsBrowseBtn")
        browse_btn.clicked.connect(self._browse_workspace)
        workspace_row.addWidget(browse_btn)
        layout.addLayout(workspace_row)

        layout.addWidget(self._section("数据库"))
        self._db_url = self._add_field(layout, "URL", self._config.database.url)

        layout.addStretch()
        return tab

    # ── Model Tab ────────────────────────────────────────────

    def _build_model_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(self._section("模型选择"))
        self._model = self._add_field(layout, "Model", self._config.model or "")
        self._small_model = self._add_field(layout, "Small Model", self._config.small_model or "")

        layout.addWidget(self._section("Provider"))
        provider_names = ", ".join(self._config.provider.keys()) if self._config.provider else "未配置"
        layout.addWidget(QLabel(f"已配置: {provider_names}"))

        layout.addWidget(self._section("Skills"))
        self._skills_enabled = QCheckBox("启用 Skills")
        self._skills_enabled.setChecked(self._config.skills.enabled)
        layout.addWidget(self._skills_enabled)

        layout.addWidget(self._section("Agent Team"))
        self._agent_team_enabled = QCheckBox("启用 Agent Team")
        self._agent_team_enabled.setChecked(self._config.agent_team.enabled)
        layout.addWidget(self._agent_team_enabled)

        layout.addStretch()
        return tab

    # ── About Tab ────────────────────────────────────────────

    def _build_about_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("<b>IntelliAgent</b>")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px;")
        layout.addWidget(title)

        layout.addWidget(QLabel("Coding Agent 骨架项目"))
        layout.addWidget(QLabel(""))
        layout.addWidget(QLabel("配置保存到 intelliagent.json"))
        layout.addWidget(QLabel("修改后需重启应用生效"))

        layout.addStretch()
        return tab

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _section(title: str) -> QLabel:
        label = QLabel(f"<b>{title}</b>")
        label.setStyleSheet(
            "color: #5f5f5f; font-size: 12px; font-weight: 600; border-bottom: 1px solid #e5e7eb; padding-bottom: 2px;"
        )
        return label

    @staticmethod
    def _add_field(layout: QVBoxLayout, label: str, value: str) -> QLineEdit:
        row = QHBoxLayout()
        lbl = QLabel(label)
        lbl.setFixedWidth(90)
        row.addWidget(lbl)
        edit = QLineEdit(value)
        edit.setObjectName("settingsInput")
        row.addWidget(edit)
        layout.addLayout(row)
        return edit

    def _browse_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择工作区", self._workspace_dir.text())
        if path:
            self._workspace_dir.setText(path)

    # ── Save ─────────────────────────────────────────────────

    def _save(self) -> None:
        raw = {}
        if self.CONFIG_PATH.exists():
            raw = json.loads(self.CONFIG_PATH.read_text(encoding="utf-8"))

        raw["agent_id"] = self._agent_id.text()
        raw.setdefault("workspace", {})["dir"] = self._workspace_dir.text()
        raw.setdefault("database", {})["url"] = self._db_url.text()
        if self._model.text():
            raw["model"] = self._model.text()
        if self._small_model.text():
            raw["small_model"] = self._small_model.text()
        raw.setdefault("skills", {})["enabled"] = self._skills_enabled.isChecked()
        raw.setdefault("agent_team", {})["enabled"] = self._agent_team_enabled.isChecked()

        self.CONFIG_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

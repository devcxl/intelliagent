# Out-of-Scope

本文档记录在需求访谈中明确排除了的功能范围及其原因。

## GUI 扩展（PRD: docs/prd/pyqt5-gui-extension.md）

| 功能 | 排除原因 |
|------|----------|
| 深色/浅色主题切换 | P1，阶段一专注核心功能，主题不影响可用性 |
| 配置编辑面板（结构化表单） | P2，阶段一用户可通过直接修改 intelliagent.json 配置 |
| 运行时工作区切换 | P2，启动时从 intelliagent.json 加载工作区 |
| 系统托盘 / 最小化到托盘 | 未提及需求，不做 |
| QWebEngineView 渲染 | 依赖太重（~150MB），使用 mistune 轻量方案 |
| 独立进程部署（GUI 独立包） | 决定为 src/gui/ 独立模块，与 CLI 平级 |
| 集成到现有 CLI 的 --gui 参数 | 决定为独立入口 python -m src.gui.main |
| REST API / HTTP Server | 不是 GUI 的目标 |
| 移动端适配 | 桌面端专用 |
| 虚拟滚动 / 长对话优化 | 阶段一不涉及性能优化 |

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

## 架构可靠性修复（PRD: docs/prd/architecture-reliability-refactor.md）

| 功能 | 排除原因 |
|------|----------|
| 新增 Anthropic / Gemini / DeepSeek 等 Provider | 本次只建立最小 provider-neutral DTO，避免把架构修复扩展为新功能开发 |
| Memory / AgentMemory 长期记忆 | 尚未完成独立需求分析；本次反而移除未使用的预留抽象和表结构 |
| Web / REST API / 移动端入口 | 与安全、会话、事务和包边界修复无直接关系 |
| Agent Worker / Agent Bus | `docs/design/agent-worker-bus-architecture.md` 仍为 Draft，不能夹带进入本次修复 |
| 深色主题与 QFluentWidgets | 只修正文档漂移，不实现新的 GUI 视觉能力 |
| 删除、替换或降级现有 PyQt5 GUI | 本次必须保留 GUI 的现有核心用户流程，只修复其应用层边界 |
| 现有 SQLite 数据无损迁移 | 项目处于 0.1 开发阶段，维护者确认开发库允许重建 |
| 远端服务端确认取消 | LLM/MCP 协议无法统一保证；只提供本地强保证，远端取消 best-effort |
| 完整 Clean Architecture / DDD Mapper | 当前规模不需要额外层次，只实施最小 ports、service 和依赖规则 |
| 新插件框架 | 本次只修正现有 tools/skills/MCP 装配，不扩展新的插件能力 |
| 无关的新工具、入口或用户功能 | 架构修复不夹带产品功能，避免扩大验收范围 |
| 跨进程队列、分布式调度与 QPS 指标 | 当前目标为单进程本地 coding-agent skeleton |
| 性能专项、虚拟滚动、流式 token UI | 不属于本次架构正确性和可靠性目标 |
| Release、版本发布与包分发 | 自动化生命周期终点为合并，不包含 release |

# ADR 0009: Textual TUI 取代 PyQt5 GUI，配置改 YAML

## 状态

已决策，随 2026-10 重构实施。

## 背景

旧 GUI 为 PyQt5 + qasync（2,100 行，占项目近三成），存在 Qt/asyncio 桥接脆弱、直接依赖 repository 绕过 service 层等问题。配置为 `intelliagent.json` + 自研 `{env:VAR}` 插值，示例文件已与实现脱节。本次重构整体收敛技术栈。

## 决策

- **前端**：PyQt5 GUI 整体删除，改为 **Textual TUI**，形态取 pi（badlogic/pi-mono）的最简版：消息流 + 内联工具调用折叠 + 多行输入编辑器 + 底部状态栏。不做会话列表侧边栏、设置面板、主题系统。
- **无头模式**：保留非交互入口（一次性任务参数 / stdin 进、事件流出），供脚本与测试使用，不是 REPL。
- **配置**：`intelliagent.json` 删除，改为 **`intelliagent.yaml`** 单文件；`plugins:` 段统一管理插件启用与插件配置；保留环境变量插值能力。不做旧配置迁移。

## 被否决的方案

- **TUI 对齐旧 GUI 完整功能面**：工作量大，且权限确认弹窗在无捆绑 permission 插件（ADR 0008）下无意义。
- **TUI 与 CLI REPL 并存**：两套前端维护成本高，无头模式已覆盖自动化场景。

## 后果

- Textual 自带 asyncio 集成，消除 qasync 桥接层；TUI 只消费引擎事件流，不直连 persistence。
- 配置格式破坏性变更，旧 `intelliagent.json` 不再被读取（删除胜过兼容）。

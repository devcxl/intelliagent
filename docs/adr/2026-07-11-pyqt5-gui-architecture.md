# ADR 0007: PyQt5 GUI 扩展架构

## 状态

Accepted

## 背景

IntelliAgent 仅有 CLI 界面（`src/cli/`），通过终端 REPL 交互。为降低使用门槛并验证核心的事件驱动架构可对接不同前端，需要提供一个 GUI 界面。

核心约束：
- **零修改**：GUI 不能修改 `src/core/`、`src/runtime/`、`src/db/` 的现有代码
- **事件驱动对接**：引擎以 `AsyncGenerator[dict]` 向外发射事件，前端需消费该流
- **扩展性**：GUI 是 CLI 的全功能替代品，而非子集

## 决策

### 1. 独立模块，非独立包

GUI 放在 `src/gui/` 下，与 `src/cli/` 同级，而非独立包。

理由：
- 共享 Python 解释器和依赖，无需 socket/IPC
- 直接 import 核心模块，类型检查天然支持
- 不增加打包复杂度

### 2. qasync 桥接 asyncio ↔ Qt

使用 `qasync` 库让 asyncio 事件循环驱动 Qt 主线程，而非 QThread 代理。

理由：
- 引擎 `iter_steps()` 是 async generator，qasync 天然适配
- 无需跨线程信号/槽同步，避免竞态
- 代码更简洁：`await` 直接消费事件流，`pyqtSignal` 推送到 UI

### 3. QFluentWidgets 作为 UI 组件库

使用 QFluentWidgets 提供 Fluent Design 风格的组件。

理由：
- 内置浅色/深色主题切换（阶段二 P1）
- 现代化外观，减少手写样式代码
- 活跃维护的 PyQt5/PySide6 兼容库

### 4. PermissionDialog 模态阻塞代替 CliCallback

CLI 的 `CliCallback` 有 120s 超时自动拒绝。GUI 版本使用 `QDialog.exec()` 模态阻塞，无超时。

理由：
- 图形化弹窗比终端输入更自然
- 模态确保用户必须处理后才能继续
- 无超时避免 LLM 决策因超时被打断

### 5. mistune 渲染 Markdown，不用 QWebEngine

LLM 回答中的 Markdown（代码块、列表、加粗）通过 mistune 解析为 HTML，再通过 `QTextEdit.setHtml()` 渲染。

理由：
- 避免 QWebEngineView 的 ~150MB 依赖
- mistune 3.x 是纯 Python，轻量快速
- QTextEdit 支持 HTML 子集，覆盖常见 Markdown 语法

### 6. 事件流逐条追加渲染

引擎每 yield 一个事件，ChatView 立即追加渲染对应组件，不等整轮完成。

理由：
- 用户实时看到 LLM 思考过程，降低等待焦虑
- 支持后续实现打字机效果
- 事件类型与 UI 组件一一对应，映射清晰

## 后果

正面：
- GUI 不修改核心一行代码，验证架构的扩展性
- 逐事件渲染提供实时反馈
- 模态权限弹窗避免 CLI 超时问题

负面：
- 引入 qasync + PyQt5 + QFluentWidgets 三个 GUI 依赖
- mistune 渲染代码块不如 QWebEngine 丰富（无 JS 语法高亮）
- 长对话上千条消息时可能需虚拟滚动优化（阶段一不做）

## 兼容性

- ADR 0001（Context Summary Compression）：无影响，GUI 不修改 ContextManager
- ADR 0002（Config Unification）：GUI 复用 UnifiedConfig，无变化
- ADR 0003（Permission Redesign）：GUI 实现新的 PermissionCallback，兼容现有 PermissionEngine
- ADR 0004（Skill Mechanism）：无影响
- ADR 0005（Agent Team）：GUI 暂不涉及
- ADR 0006（SOLID Refactor）：无影响

## 非目标

- 不做系统托盘
- 不做 REST API / HTTP Server
- 不做移动端适配
- 不做虚拟滚动优化（阶段一）

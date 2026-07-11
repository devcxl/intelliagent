## 设计方案

### 架构概述
GUI 扩展为独立模块 `src/gui/`，与 `src/cli/` 平级，只 import 不修改核心代码。

### 关键技术决策
| 决策 | 选择 |
|------|------|
| 入口 | `python -m src.gui.main` |
| 事件桥接 | qasync（asyncio → Qt） |
| UI 组件库 | QFluentWidgets |
| Markdown | mistune |
| 渲染模式 | 逐事件追加 |
| 依赖管理 | optional-dependencies `[gui]` |

### 模块设计
- **EventBridge**: AsyncGenerator → pyqtSignal，消费引擎事件流
- **ChatView**: 按事件类型渲染 MessageBubble（thought/action/observation/answer）
- **SessionList**: 侧边栏，复用 ConversationService 实现 CRUD
- **PermissionDialog**: 模态弹窗，替代 CliCallback，无超时
- **InputBar**: 输入框 + 斜杠命令解析

### 阶段规划
- **阶段一**（P0）：聊天 + 会话管理 + 权限弹窗
- **阶段二**（P1）：深色/浅色主题
- **阶段三**（P2）：配置面板 + 工作区切换

### 完整文档
- 技术方案：`docs/dev/specs/pyqt5-gui-extension.md`
- ADR：`docs/adr/2026-07-11-pyqt5-gui-architecture.md`
- PRD：`docs/prd/pyqt5-gui-extension.md`

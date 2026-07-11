# PRD: PyQt5 GUI 扩展

- **状态**: Draft
- **创建日期**: 2026-07-11
- **标签**: `enhancement`, `gui`, `pyqt5`

## 1. 背景与动机

IntelliAgent 目前仅有 CLI 交互界面（`src/cli/`），通过终端 REPL 循环与用户交互。CLI 模式对以下场景存在局限：

- **可视化缺失**：LLM 的思考过程、工具调用、观测结果均以纯文本堆叠输出，难以快速定位关键信息
- **会话管理不直观**：历史会话需通过 `--history` 参数列出，`--resume` 或 `--session` 参数恢复，缺乏图形化点选操作
- **权限交互割裂**：权限弹窗（`CliCallback`）嵌在终端中，有 120s 超时限制，无法阻塞等待用户确认
- **入门门槛**：终端界面对于非 CLI 熟悉用户不友好

**目标**：提供一个 PyQt5 GUI 作为 CLI 的全功能替代品，覆盖多轮对话、会话管理、权限交互等核心使用路径。

### 业务价值

- **降低使用门槛**：GUI 图形界面比 CLI 更易于新用户上手
- **提升交互效率**：可视化呈现工具调用链、会话列表操作、快速切换
- **架构示范**：验证 `src/core/` 的事件驱动架构可与任意前端（CLI / GUI / Web）对接

### 成功指标

- 用户可以完成完整的「输入问题 → 看到流式回复 → 查看工具调用卡片 → 切换/管理会话」闭环
- 权限交互不超时，用户确认/取消行为清晰反馈
- 不修改 `src/core/`、`src/runtime/`、`src/db/` 一行代码（纯扩展）

## 2. 用户故事

### US-01：多轮对话

> 作为用户，我可以在输入框中输入自然语言问题，看到 LLM 的思考过程、工具调用结果和最终回答，所有消息以流式方式逐条呈现。

**验收标准**：
- 输入框输入文本按回车/点击发送，对话区立即开始流式渲染
- thought 事件以灰色斜体文本呈现
- tool_call 事件以可折叠 JSON 卡片呈现（显示工具名 + 参数）
- observation 事件以回显块呈现
- answer 事件以 Markdown 渲染（代码块、列表、加粗等）
- LLM 回复时，对话区自动滚动到最新消息

### US-02：会话管理

> 作为用户，我可以查看所有历史会话，点击切换会话自动 resume 并加载历史消息，也可以创建新会话或删除会话。

**验收标准**：
- 左侧侧边栏列出所有历史会话（显示标题、时间戳）
- 点击某会话 → 右侧对话区加载该会话的全部历史消息
- 点击「新建会话」按钮或输入 `/new` → 创建空会话并切换到它
- 会话列表支持删除（右键菜单或 `/delete` 命令）
- 列表实时反映新增/删除状态

### US-03：权限交互

> 当 LLM 请求执行高风险操作（如写文件、执行命令）时，GUI 弹出确认对话框，不超时，阻塞等待用户确认或取消。

**验收标准**：
- 工具调用触发 "ask" 权限时弹出模态对话框
- 对话框显示：工具名称、参数、风险原因
- 无超时限制，用户不操作则界面阻塞
- 用户点击「允许」→ 工具继续执行
- 用户点击「拒绝」→ 告知 LLM "用户已取消该操作"
- 权限对话框保持模态，不允许后台交互

### US-04：斜杠命令

> 我可以通过斜杠命令快速操作，如新建会话、删除会话、打开配置面板等。

**验收标准**：
- 输入 `/new` → 创建新会话
- 输入 `/delete` → 删除当前会话
- 输入 `/resume <id>` → 切换到指定会话
- 不认识的命令 → 显示可用命令列表

## 3. 范围

### In Scope (P0)

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 流式对话渲染 | P0 | thought → tool_call → observation → answer 逐事件渲染 |
| 工具调用卡片 | P0 | 可折叠 JSON 卡片，显示工具名和参数 |
| Markdown 渲染 | P0 | LLM 回答中的代码块、列表、加粗等 |
| 会话侧边栏 | P0 | 历史会话列表，点击切换 |
| 会话 CRUD | P0 | 新建、切换、删除（增删查改） |
| 权限弹窗 | P0 | 模态对话框，无超时，确认/取消反馈 |
| Event Bridge | P0 | AsyncGenerator → Qt Signal 桥接 |
| 斜杠命令 | P0 | /new, /delete, /resume |

### In Scope (P1 — 可延后)

| 功能 | 优先级 | 说明 |
|------|--------|------|
| 深色/浅色主题 | P1 | 通过 QFluentWidgets 切换 |
| 配置面板 | P2 | 结构化表单编辑 intelliagent.json |
| 工作区切换 | P2 | 运行时选择项目目录 |

### Out of Scope

详见 `docs/dev/out-of-scope.md`。

## 4. 技术约束

| 约束项 | 要求 |
|--------|------|
| 语言 | Python 3.11+ |
| UI 框架 | PyQt5 + QFluentWidgets |
| 事件桥接 | qasync |
| Markdown | mistune |
| 核心修改 | **不允许**修改 src/core/、src/runtime/、src/db/ 的代码 |
| 依赖管理 | optional-dependencies `[gui]`，不强依赖 |
| 启动入口 | `python -m src.gui.main`，独立入口 |
| 构建工具 | uv（包管理），不引入额外构建系统 |

## 5. 架构概览

```
src/gui/          ← 新增独立模块
├── main.py          入口
├── main_window.py   主窗口布局
├── widgets/         组件
│   ├── chat_view.py
│   ├── message_bubble.py
│   ├── input_bar.py
│   ├── session_list.py
│   └── permission_dialog.py
├── services/        桥接服务
│   ├── event_bridge.py
│   └── command_parser.py
└── styles/          样式
    ├── theme.py
    └── markdown.py
```

关键技术决策已在 ADR 中记录（后续阶段输出）。

## 6. 依赖关系

GUI 模块对核心模块的依赖（只 import，不修改）：

```
src/gui/ → src/runtime/agent_runtime.py (AgentRuntime)
        → src/db/repositories/...    (ConversationRepository, MessageRepository)
        → src/permission/engine.py    (PermissionEngineProtocol)
        → src/config/unified_config.py (UnifiedConfig)
        → src/types/                  (LLMClientProtocol, etc.)
```

## 7. 验收标准汇总

1. **聊天闭环**：输入问题 → 看到流式 LLM 回复，工具调用以卡片形式展示
2. **会话管理**：侧边栏列出所有会话，支持新建/切换/删除，点击会话自动 resume + 加载历史
3. **权限交互**：权限弹窗模态阻塞，无超时，确认/取消有明确反馈
4. **斜杠命令**：/new, /delete, /resume 可用
5. **零核心修改**：不修改 src/core/, src/runtime/, src/db/ 的代码

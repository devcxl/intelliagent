---
name: "gui-chat-view"
depends_on: ["gui-scaffold"]
labels: ["gui"]
worktree_root: ".worktree/gui-chat-view/"
---

## 目标

实现对话区渲染：消息气泡、工具调用卡片、输入框、斜杠命令、Markdown 渲染。

## 实现要点

### MarkdownRenderer (`src/gui/styles/markdown.py`)
- mistune 解析 Markdown → HTML
- QTextEdit.setHtml() 渲染
- 代码块用等宽字体 + 灰色背景

### MessageBubble (`src/gui/widgets/message_bubble.py`)
- `user` 类型：蓝色背景右对齐
- `thought` 类型：灰色斜体 QLabel
- `tool_call` 类型：可折叠卡片（QFrame + 点击展开），标题显示工具名
- `observation` 类型：深色背景 + 等宽字体 QTextEdit
- `answer` 类型：Markdown 渲染的 QTextEdit

### ChatView (`src/gui/widgets/chat_view.py`)
- QScrollArea，垂直布局
- `append_event(event: dict)` — 根据 event 类型追加对应 MessageBubble
- 自动滚动到底部

### InputBar (`src/gui/widgets/input_bar.py`)
- QLineEdit + QPushButton「发送」
- 按回车 / 点击按钮发射 `submitted` signal
- 输入前（引擎运行中）禁用发送按钮
- 支持 `/new`, `/delete`, `/resume <id>`, `/help` 命令

### CommandParser (`src/gui/services/command_parser.py`)
- `/new` → 调用 ConversationService 创建 + 切换
- `/delete` → 删除当前会话
- `/resume <id>` → 切换到指定会话
- `/help` → 显示可用命令列表
- 解析成功返回 `(command_type, args)` 结构

## 验收标准

- [ ] user 消息显示为右对齐气泡
- [ ] thought 显示为灰色斜体
- [ ] tool_call 显示为可折叠卡片（标题 + 展开参数）
- [ ] observation 显示为等宽字体回显
- [ ] answer 用 Markdown 渲染（代码块、列表、加粗）
- [ ] 引擎运行时发送按钮禁用
- [ ] /new 触发新建会话
- [ ] /help 显示命令列表

## Worktree
- 路径: `.worktree/gui-chat-view/`
- 分支: `feat/gui-chat-view`
- 创建时机: `/code` 阶段首次执行时自动创建
- 清理时机: PR 合并后自动删除

---
name: "gui-session-list"
depends_on: ["gui-scaffold"]
labels: ["gui"]
worktree_root: ".worktree/gui-session-list/"
---

## 目标

实现左侧会话列表侧边栏，支持列出、切换、新建、删除对话。

## 实现要点

### SessionList (`src/gui/widgets/session_list.py`)
- QListWidget / QListView 风格列表，置于左侧
- 数据来源：`ConversationService.list_conversations()`
- 每项显示：会话标题（取第一条消息摘要或 "新对话"）+ 时间戳
- 操作：
  - **单击** → 切换会话 → `EventBridge.resume_session(id)` → 加载历史消息到 ChatView
  - **顶部 [+]** 按钮 → 新建空会话
  - **右键菜单 / Delete 键** → 删除确认 → 删除会话
- 会话切换时，ChatView 清空并重新加载历史消息
- 新建会话时，ChatView 清空为空白状态

### 关键集成
- 通过 signal 通知 MainWindow 切换事件
- 导入 `ConversationService` 从 `src.db.repositories.conversation`
- 也导入 `MessageRepository` 用于加载历史消息

## 验收标准

- [ ] 侧边栏列出所有历史会话（标题 + 时间）
- [ ] 单击会话 → ChatView 加载该会话历史消息
- [ ] [+] 按钮 → 新建空白会话并切换到它
- [ ] 右键删除 → 确认后删除
- [ ] 列表在新增/删除后实时刷新

## Worktree
- 路径: `.worktree/gui-session-list/`
- 分支: `feat/gui-session-list`
- 创建时机: `/code` 阶段首次执行时自动创建
- 清理时机: PR 合并后自动删除

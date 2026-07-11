---
name: "gui-main-window"
depends_on: ["gui-event-bridge", "gui-chat-view", "gui-session-list"]
labels: ["gui"]
worktree_root: ".worktree/gui-main-window/"
---

## 目标

组装 MainWindow：Discord 风格双栏布局，连接 EventBridge ↔ ChatView ↔ SessionList，实现完整的 main.py 入口。

## 实现要点

### MainWindow (`src/gui/main_window.py`)
- `QMainWindow` 子类
- 布局：
  ```
  ┌──────────────┬─────────────────────────────────┐
  │ SessionList   │  ChatView                        │
  │ (固定宽度)    │  (拉伸)                          │
  │              │  ─────────────────────────────── │
  │              │  InputBar (底部，固定高度)        │
  └──────────────┴─────────────────────────────────┘
  ```
- EventBridge 信号连接：
  - `event_received` → `ChatView.append_event()`
  - `engine_started` → `InputBar.setEnabled(False)` + 状态指示
  - `engine_finished` → `InputBar.setEnabled(True)`
  - `error_occurred` → QMessageBox 显示错误
- SessionList 切换 → ChatView 清空 + 加载历史
- 显示状态栏（当前会话 ID + 引擎状态）

### `src/gui/main.py`（最终入口）
```python
async def main():
    # 1. 创建 QApplication + qasync
    # 2. 加载 UnifiedConfig
    # 3. 创建 AgentRuntime
    # 4. runtime.initialize()
    # 5. 创建 EventBridge
    # 6. 创建 MainWindow(event_bridge)
    # 7. 加载默认会话
    # 8. main_window.show()
    # 9. app.exec()

if __name__ == "__main__":
    qasync.run(main())
```

### ThemeManager (`src/gui/styles/theme.py`)
```python
class ThemeManager:
    @staticmethod
    def apply_light(qapp: QApplication):
        # QFluentWidgets 浅色主题
        ...

    @staticmethod
    def apply_dark(qapp: QApplication):
        # QFluentWidgets 深色主题
        ...
```
阶段一只用浅色主题，主题切换为 P1。

## 验收标准

- [ ] Python -m src.gui.main 启动完整 GUI
- [ ] 左侧显示会话列表，右侧显示对话区 + 输入框
- [ ] 输入问题 → LLM 回复流式渲染
- [ ] 工具调用显示卡片
- [ ] 切换会话 → 加载历史消息
- [ ] 状态栏显示当前状态
- [ ] 应用关闭时 runtime.shutdown() 正确清理

## Worktree
- 路径: `.worktree/gui-main-window/`
- 分支: `feat/gui-main-window`
- 创建时机: `/code` 阶段首次执行时自动创建
- 清理时机: PR 合并后自动删除

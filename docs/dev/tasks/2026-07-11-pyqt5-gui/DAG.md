# DAG: PyQt5 GUI 扩展

```mermaid
graph TD
  %% Batch 1
  A["scaffold<br/>项目脚手架"] --> B["event-bridge<br/>事件桥接 + 权限弹窗"]
  A --> C["chat-view<br/>对话视图"]
  A --> D["session-list<br/>会话列表"]

  %% Batch 3
  B --> E["main-window<br/>主窗口集成"]
  C --> E
  D --> E
```

## 拓扑顺序

| Batch | Task | 并行？ | 依赖 |
|-------|------|--------|------|
| 1 | scaffold | - | 无 |
| 2 | event-bridge, chat-view, session-list | ✅ 可并行 | scaffold |
| 3 | main-window | - | event-bridge, chat-view, session-list |

## 任务清单

| 任务 | 文件 | 分支 | 工时估计 |
|------|------|------|----------|
| scaffold | 7 个 | feat/gui-scaffold | 30min |
| event-bridge | 2 个 | feat/gui-event-bridge | 1h |
| chat-view | 5 个 | feat/gui-chat-view | 2h |
| session-list | 1 个 | feat/gui-session-list | 1h |
| main-window | 2 个 | feat/gui-main-window | 1h |

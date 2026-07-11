---
name: "gui-event-bridge"
depends_on: ["gui-scaffold"]
labels: ["gui"]
worktree_root: ".worktree/gui-event-bridge/"
---

## 目标

实现 `EventBridge`（AsyncGenerator → Qt Signal 桥接）和 `PermissionDialog`（模态权限弹窗）。

## 实现要点

### EventBridge (`src/gui/services/event_bridge.py`)

```python
class EventBridge(QObject):
    event_received = pyqtSignal(dict)       # thought/action/observation/answer
    engine_started = pyqtSignal()
    engine_finished = pyqtSignal(dict)      # {success, answer, ...}
    error_occurred = pyqtSignal(str)

    def __init__(self, runtime: AgentRuntime):
        ...

    async def submit_task(self, text: str):
        # asyncio.create_task 消费 engine.iter_steps()
        ...

    def cancel(self):
        # 取消当前任务
        ...
```

- 导入 `AgentRuntime` 从 `src.runtime.agent_runtime`
- 每个事件通过 `pyqtSignal` 发射到主线程

### PermissionDialog (`src/gui/widgets/permission_dialog.py`)

```python
class PermissionDialog(QDialog):
    # 实现 PermissionCallbackProtocol
    @classmethod
    async def on_prompt(cls, tool_name: str, args: dict, reason: str) -> bool:
        # QDialog.exec() 模态阻塞，无超时
        ...
```

- 模态对话框，无超时
- 显示工具名、参数信息、风险原因
- 两个按钮：「允许」「拒绝」
- 拒绝时返回 False，ChatView 显示"用户已取消该操作"

## 验收标准

- [ ] EventBridge 在同步上下文中可实例化
- [ ] PermissionDialog 弹出显示工具名和参数
- [ ] 点击「允许」返回 True
- [ ] 点击「拒绝」返回 False
- [ ] 模态阻塞期间不能操作主窗口

## Worktree
- 路径: `.worktree/gui-event-bridge/`
- 分支: `feat/gui-event-bridge`
- 创建时机: `/code` 阶段首次执行时自动创建
- 清理时机: PR 合并后自动删除

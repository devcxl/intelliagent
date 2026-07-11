# 技术方案：PyQt5 GUI 扩展

- **状态**: Draft
- **创建日期**: 2026-07-11
- **关联 Issue**: [#35](https://github.com/devcxl/intelliagent/issues/35)
- **关联 PRD**: `docs/prd/pyqt5-gui-extension.md`

## 1. 技术选型

| 选型 | 选择 | 理由 |
|------|------|------|
| UI 框架 | PyQt5 | 用户指定；生态成熟，Python Qt 绑定首选 |
| 组件库 | QFluentWidgets | 现代化 Fluent Design 风格，内置浅色/深色主题切换 |
| 事件桥接 | qasync | 让 asyncio 事件循环在 Qt 主线程运行，无需多线程同步问题 |
| Markdown 渲染 | mistune | 轻量级（无 150MB QWebEngine 依赖），纯文本渲染 |
| 依赖管理 | optional-dependencies `[gui]` | 不强依赖，不增加非 GUI 用户的安装成本 |

## 2. 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  src/gui/                                                     │
│  ┌─────────────────────────────────────────────────┐          │
│  │  QApplication (qasync event loop)               │          │
│  │                                                   │          │
│  │  ┌──────────┐  ┌──────────────────────────┐     │          │
│  │  │ Session  │  │  Chat Area                │     │          │
│  │  │ List     │  │  ┌────────────────────┐   │     │          │
│  │  │          │  │  │ MessageBubble[]    │   │     │          │
│  │  │ /session1│  │  │ - user (plain)     │   │     │          │
│  │  │ /session2│  │  │ - thought (gray)   │   │     │          │
│  │  │ /session3│  │  │ - tool_call (card) │   │     │          │
│  │  │          │  │  │ - observation (回显) │   │     │          │
│  │  │ [+] 新建 │  │  │ - answer (md)      │   │     │          │
│  │  └──────────┘  │  └────────────────────┘   │     │          │
│  │                 │  ┌────────────────────┐   │     │          │
│  │                 │  │ InputBar           │   │     │          │
│  │                 │  │ [/new, /delete...] │   │     │          │
│  │                 │  └────────────────────┘   │     │          │
│  │                 └──────────────────────────┘     │          │
│  │                                                   │          │
│  │  ┌──────────────────────────────────────────┐     │          │
│  │  │ PermissionDialog (modal)                 │     │          │
│  │  │ 工具: write_file / 参数: {path: ...}      │     │          │
│  │  │ [允许] [拒绝]                             │     │          │
│  │  └──────────────────────────────────────────┘     │          │
│  └─────────────────────────────────────────────────┘          │
│                                                               │
│  ┌──────────────── Services ────────────────────────┐          │
│  │ EventBridge: AsyncGenerator → pyqtSignal         │          │
│  │ CommandParser: /cmd → handler                   │          │
│  └─────────────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
         │ 使用（只 import，不修改）
         ▼
┌──────────────────────────────────────────────────────────────┐
│  src/runtime/agent_runtime.py   (AgentRuntime)               │
│  src/db/repositories/           (ConversationRepository)     │
│  src/permission/engine.py       (PermissionEngineProtocol)   │
│  src/config/unified_config.py   (UnifiedConfig)              │
│  src/types/                     (LLMClientProtocol)          │
└──────────────────────────────────────────────────────────────┘
```

## 3. 模块设计

### 3.1 EventBridge（事件桥接）

**职责**：将 `ReactEngine` 的异步事件生成器适配到 Qt 信号系统。

```
User Input
    │
    ▼
EventBridge.submit_task(text)
    │
    ├── asyncio.create_task(_run_engine(text))
    │     │
    │     ├── AgentRuntime.execute(task)
    │     │     └── async for event in engine.iter_steps():
    │     │           pyqtSignal.emit(event)    ← 跨线程安全
    │     │
    │     └── engine loop ends
    │
    └── ChatView 连接 signal → append_event(event)
```

**核心类**：

```python
class EventBridge(QObject):
    event_received = pyqtSignal(dict)      # thought/action/observation/answer
    engine_started = pyqtSignal()
    engine_finished = pyqtSignal(dict)     # {success, answer, ...}
    error_occurred = pyqtSignal(str)

    def __init__(self, runtime: AgentRuntime):
        self._runtime = runtime
        self._task: asyncio.Task | None = None

    async def submit_task(self, text: str):
        """提交用户输入，启动引擎异步消费"""
        self.engine_started.emit()
        async for event in self._runtime.execute(text):
            self.event_received.emit(event)
        # engine finished
        self.engine_finished.emit(...)

    def cancel(self):
        if self._task and not self._task.done():
            self._task.cancel()
```

### 3.2 ChatView（对话区）

**职责**：接收事件流，按类型渲染为不同的消息组件。

```
ChatView (QScrollArea)
  └── layout: QVBoxLayout
        ├── MessageBubble(type="user", content)
        ├── MessageBubble(type="thought", content)
        ├── MessageBubble(type="tool_call", {name, args, result})
        ├── MessageBubble(type="observation", content)
        └── MessageBubble(type="answer", content)  [Markdown rendered]
```

render 策略：

| 事件类型 | 渲染组件 | 说明 |
|---------|---------|------|
| `thought` | QLabel + 灰色斜体 | 思考文本 |
| `action` | ToolCard (可折叠 QFrame) | 标题：工具名，内容：参数 JSON |
| `observation` | QFrame + 等宽字体 | 工具执行结果回显 |
| `answer` | QTextEdit + mistune HTML | Markdown 渲染，代码块语法高亮 |

### 3.3 MessageBubble（消息气泡）

**职责**：单一消息类型的渲染单元。

- `user`：蓝色背景右对齐
- `thought`：灰色斜体，小字号
- `tool_call`：可折叠卡片，标题显示工具名（如 `🔧 read_file`），点击展开参数
- `observation`：深色背景，等宽字体
- `answer`：mistune HTML 渲染，代码块用 QTextEdit

### 3.4 InputBar（输入框）

**职责**：文本输入 + 斜杠命令解析 + 发送按钮。

```python
class InputBar(QWidget):
    submitted = pyqtSignal(str)         # 用户按回车/发送按钮

    # 内部委托 CommandParser
    # 若输入以 / 开头 → CommandParser.parse(cmd)
    # 否则 → submitted.emit(text)
```

### 3.5 CommandParser（命令解析）

```python
class CommandParser:
    handlers: dict[str, Callable] = {
        "/new":     lambda: session_service.create(),
        "/delete":  lambda: session_service.delete(current_id),
        "/resume":  lambda id: session_service.switch_to(id),
        "/help":    lambda: show_help(),
    }

    def parse(self, text: str) -> bool:
        """返回 True 如果是命令且已处理，False 则是普通对话"""
```

### 3.6 SessionList（会话列表）

**职责**：左侧栏显示所有历史会话，支持 CRUD。

- 数据来源：`ConversationService.list_conversations()`
- 操作：
  - 点击 → `EventBridge.resume_session(id)` → 加载历史消息
  - 右键 → 删除
  - `[+]` 按钮 → 新建

### 3.7 PermissionDialog（权限对话框）

**职责**：替代 `CliCallback`，实现 `PermissionCallbackProtocol`。

```python
class PermissionDialog(QDialog):
    accepted = pyqtSignal()
    rejected = pyqtSignal()

    @classmethod
    async def on_prompt(cls, tool_name: str, args: dict, reason: str) -> bool:
        """静态方法，实现 PermissionCallbackProtocol 接口"""
        dialog = cls(tool_name, args, reason)
        dialog.exec()           # 模态阻塞，无超时
        return dialog.result() == QDialog.Accepted
```

### 3.8 Theme（主题管理）

**职责**：封装 QFluentWidgets 主题切换。

```python
class ThemeManager:
    @staticmethod
    def apply_light(qapp: QApplication): ...
    @staticmethod
    def apply_dark(qapp: QApplication): ...
```

P1 实现，阶段一仅固定为浅色主题。

## 4. 数据流

### 4.1 启动流程

```
python -m src.gui.main
    │
    ├── 1. 创建 QApplication + qasync QEventLoop
    ├── 2. 加载 UnifiedConfig ("intelliagent.json")
    ├── 3. 创建 AgentRuntime(config)
    ├── 4. runtime.initialize()        # DB + MCP
    ├── 5. 创建 EventBridge(runtime)
    ├── 6. 创建 MainWindow → 布局各组件
    ├── 7. 加载最新/默认会话 → 显示历史消息
    └── 8. app.exec() → qasync loop
```

### 4.2 一轮对话

```
用户输入 "帮我看看当前目录结构"
    │
    ├── InputBar.submitted.emit("帮我看看当前目录结构")
    │
    ├── EventBridge.submit_task("帮我看看当前目录结构")
    │     │
    │     ├── ConversationSession.run_turn("帮我看看当前目录结构")
    │     │     ├── user message → DB
    │     │     └── ReactEngine.iter_steps()
    │     │           ├── yield thought("我来查看目录...")
    │     │           ├── yield action("run_shell", {command: "ls -la"})
    │     │           ├── yield observation("total 42\n...")
    │     │           ├── yield thought("我看到了这些文件...")
    │     │           └── yield answer("当前目录包含以下内容：...")
    │     │
    │     └── (每个 event → pyqtSignal → ChatView)
    │
    └── ChatView:
          ├── 追加 "我来查看目录..." (灰色斜体)
          ├── 追加 ToolCard("run_shell", {command: "ls -la"})
          ├── 追加 observation 回显块
          └── 追加 Markdown 渲染的最终回答
```

### 4.3 权限弹窗流程

```
LLM 请求执行 write_file("foo.txt")
    │
    ├── PermissionEngine.check("write_file", {path: "foo.txt"})
    │     └── → Decision(action="ask")
    │
    ├── PermissionDialog.on_prompt("write_file", {path: "foo.txt"})
    │     └── 模态阻塞，等待用户操作
    │           ├── [允许] → return True → 工具执行
    │           └── [拒绝] → return False → "用户已取消"
    │
    └── ChatView 显示工具调用结果卡片
```

## 5. 依赖关系

### 新增依赖（optional-dependencies `[gui]`）

```
pyproject.toml:
[project.optional-dependencies]
gui = [
    "PyQt5>=5.15",
    "QFluentWidgets>=1.6",
    "qasync>=0.27",
    "mistune>=3.0",
]
```

### 对核心模块的依赖

```
src/gui/  → src/runtime/agent_runtime.py      (AgentRuntime)
           → src/db/repositories/             (ConversationRepository, MessageRepository)
           → src/permission/types.py           (PermissionCallbackProtocol)
           → src/config/unified_config.py      (UnifiedConfig)
           → src/types/llm.py                  (类型引用)
```

**零修改约束**：GUI 模块只 `import`，不修改核心模块的代码。

## 6. 测试策略

| 测试类型 | 范围 | 方式 |
|---------|------|------|
| 单元测试 | EventBridge | mock AgentRuntime，验证信号发射 |
| 单元测试 | CommandParser | 测试 /new /delete 等命令解析 |
| 单元测试 | MessageBubble | 验证不同类型渲染 |
| 集成测试 | PermissionDialog | mock PermissionEngine，验证弹窗流程 |
| e2e（手动） | 全链路 | 人工操作验证对话→会话→权限闭环 |

## 7. 风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| qasync + QFluentWidgets 事件循环冲突 | 界面卡死 | 阶段一先做最小验证 prototype |
| mistune 渲染代码块格式丢失 | 阅读体验差 | 备选：QSyntaxHighlighter 增强 |
| AgentRuntime 当前仅支持单轮 execute | 无法流式 | 已确认 iter_steps 可用 |
| PermissionCallback 异步签名 | 集成复杂 | PermissionDialog 静态方法封闭复杂性 |

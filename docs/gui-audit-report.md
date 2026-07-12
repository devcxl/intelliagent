# GUI 质量审计报告

- **作者**: Agent
- **日期**: 2026-07-12
- **范围**: `src/gui/` 全部 16 个文件
- **参考**: `DESIGN.md`（MiniMax 设计系统）、`docs/prd/pyqt5-gui-extension.md`（PRD）、`docs/dev/specs/pyqt5-gui-extension.md`（技术方案）

---

## 目录

1. [P0 — 致命缺陷（功能完全不可用）](#p0--致命缺陷功能完全不可用)
2. [P1 — 严重问题（体验极差）](#p1--严重问题体验极差)
3. [P2 — 次要问题](#p2--次要问题)
4. [事件管道完整追溯](#事件管道完整追溯)
5. [修复路线图](#修复路线图)

---

## P0 — 致命缺陷（功能完全不可用）

### P0-1：引擎事件 → UI 的数据转换链路彻底断裂

**文件**: `src/gui/main_window.py:159-166`
**严重性**: 阻塞级 — 所有后端事件无法正确渲染到前端

#### 根因

`_on_event_safe` 方法对核心引擎事件结构的假设完全错误。它用统一的 `data.get("content", ...)` 提取内容，但核心引擎的事件根本没有 `content` 顶层字段。

当前代码：

```python
def _on_event_safe(self, event: dict) -> None:
    event_type = event.get("type", "answer")
    data = event.get("data", event)
    content = data.get("content", str(data))
    self._chat_view.append_event({"type": event_type, "content": content})
```

这段代码不了解核心引擎 `src/core/events.py` 产生的五种事件结构：

#### 事件结构对照表

| 事件类型 | `event["data"]` 真实结构 | `data.get("content")` | 实际效果 |
|---------|------------------------|----------------------|---------|
| `thought` | `{content, has_tool_calls, tool_calls}` | ✅ 正确 | ✅ 正常 |
| `action` | `{tool: "工具名", args: {...}}` | ❌ KeyError | → `str(dict)` = 工具名和参数全部丢失 |
| `observation` | `{tool_name, tool_args, result, status, ...}` | ❌ KeyError | → `str(dict)` = 结果变为 Python 字符串 |
| `answer` | `{answer: "回复文本", num_turns, tokens...}` | ❌ KeyError | → `str(dict)` = **LLM 回复文字完全丢失！** |

#### 影响

1. **answer 事件**：用户看到的不是 LLM 回复，而是 `"{'answer': '...', 'num_turns': 1, ...}"` 这样的 Python dict 字符串
2. **action 事件**：`_ToolCallMsg.__init__` 需要 `data.get("name")` 和 `data.get("args")`，但传入的 data 是 `{type: "action", content: "{tool: ...}"}` → 工具名始终显示为 `?`，参数为 `（无参数）`
3. **observation 事件**：`_ObservationMsg` 接收到的 content 是整个 dict 的字符串表示

#### 为什么测试时没发现

GUI 没有单元测试。如果存在测试，第一个 `answer_event` 的解析就会暴露这个问题。

#### 修复方案

```python
def _on_event_safe(self, event: dict) -> None:
    event_type = event.get("type", "answer")
    data = event.get("data", {})

    if event_type == "thought":
        self._chat_view.append_event({
            "type": "thought",
            "content": data.get("content", ""),
        })
    elif event_type == "action":
        self._chat_view.append_event({
            "type": "action",
            "name": data.get("tool", "?"),
            "args": data.get("args", {}),
        })
    elif event_type == "observation":
        self._chat_view.append_event({
            "type": "observation",
            "content": data.get("result", str(data)),
        })
    elif event_type == "answer":
        self._chat_view.append_event({
            "type": "answer",
            "content": data.get("answer", str(data)),
        })
    else:
        self._chat_view.append_event({
            "type": event_type,
            "content": str(data),
        })
```

---

### P0-2：消息气泡内联样式与全局 QSS 完全脱节

**文件**: `src/gui/widgets/message_bubble.py:45-60` + `src/gui/styles/minimax_qss.py:144-208`
**严重性**: 阻塞级 — 所有气泡样式异常

#### 根因

`_bubble_widget` 创建 QFrame 时使用 `objectName = "chatBubble"`，但 QSS 中定义的 objectName 是 `#userBubble` 和 `#answerBubble`。两者完全不匹配。

```python
# message_bubble.py — 内联样式（优先级高，覆盖 QSS）
bubble.setObjectName("chatBubble")
bubble.setStyleSheet(
    f"#chatBubble {{ background-color: {bubble_color}; border-radius: 16px; padding: 10px 14px; }}"
)
```

```css
/* minimax_qss.py — 这些选择器永远匹配不到 */
QFrame#userBubble { background-color: #0a0a0a; border-radius: 12px; padding: 10px 16px; }
QFrame#answerBubble { border: none; margin: 4px 0; padding: 4px 0; }
```

因为 `setStyleSheet()` 内联样式优先于全局 QSS，QSS 中 `#chatBubble` 以外的所有气泡规则都成了死代码。

#### 具体偏差

| 属性 | 内联值 (message_bubble.py) | QSS 值 (minimax_qss.py) | 设计系统 (DESIGN.md) |
|------|---------------------------|------------------------|---------------------|
| 用户气泡背景色 | `#0a0a0a` (硬编码) | `#0a0a0a` (primary) | `{colors.primary}` |
| 用户气泡圆角 | `16px` (硬编码) | `12px` | `rounded.xl`: 16px (或气泡规则内 12px) |
| 用户气泡 padding | `10px 14px` | `10px 16px` | 无统一规范 |
| 气泡内字号 | `15px` (硬编码) | QSS 未定义 | body-md: 16px, body-sm: 14px |

**15px 不在设计系统中** — 既不是 body-sm(14px) 也不是 body-md(16px)。这是随意硬编码的数字。

#### 修复方案

二选一：
- **方案 A**：移除 `_bubble_widget` 的内联 `setStyleSheet`，将样式控制完全交给 QSS。`_bubble_widget` 根据调用者设置正确的 objectName（用户气泡用 `#userBubble`，助手气泡用 `#answerBubble`），不再设内联 style。颜色通过 QSS 的 `minimax_qss.py` 统一管理。
- **方案 B**：放弃 QSS 中的 `#userBubble` / `#answerBubble`，全部改用 `#chatBubble` + 内联样式。统一 font-size 为 body-md(16px)，圆角为 rounded.xl(16px)。删除 QSS 中失效的定义。

推荐方案 A（尊重设计系统）。

---

### P0-3：权限弹窗未注入到 PermissionEngine

**文件**: `src/gui/main.py:32`
**严重性**: 阻塞级 — 权限交互永远走 CLI 回调

#### 根因

`main.py` 创建 `AgentRuntime` 时使用默认 `permission_callback_factory`：

```python
runtime = AgentRuntime(config)  # ← 默认使用 CliCallback（120s 超时终端回调）
```

没有将 `PermissionDialog` 传入作为回调。导致 PermissionEngine 在做 `ask` 决策时调用的是 CLI 的 `CliCallback`，而不是 GUI 的模态对话框。用户看不到弹窗，引擎会等待终端输入直到 120 秒超时。

#### 修复方案

```python
from src.gui.widgets.permission_dialog import PermissionDialog

runtime = AgentRuntime(
    config,
    permission_callback_factory=lambda: PermissionDialog,
)
```

或者如果 `PermissionCallbackProtocol` 要求实例而不是类：

```python
runtime = AgentRuntime(
    config,
    permission_callback_factory=lambda: type("", (), {"on_prompt": PermissionDialog.on_prompt})(),
)
```

---

## P1 — 严重问题（体验极差）

### P1-1：组件大小/字号不一致 — 违反 DESIGN.md 设计系统

**涉及文件**: 多个

#### 具体偏差清单

| 位置 | 当前值 | 设计系统值 | 影响 |
|------|--------|-----------|------|
| `message_bubble.py:59` 气泡内字号 | `font-size: 15px` | body-md: 16px | 文本比预期小 |
| `message_bubble.py:50` 气泡圆角 | `border-radius: 16px` | 气泡 QSS: 12px | 圆角不一致 |
| `message_bubble.py:79` 用户消息 max-width | `setMaximumWidth(480)` 硬编码 | 无设计令牌 | 不是响应式 |
| `chat_view.py:24` 消息间距 | `setSpacing(4)` | spacing.xxs: 4px **太小** | 消息黏在一起 |
| `message_bubble.py:65` spacer 宽度 | `setFixedWidth(40)` | 无设计令牌 | 不是对齐系统 |
| `minimax_qss.py:49` 会话列表项 padding | `padding: 6px 12px` | sidebar-nav-item: `8px 16px` | 项间距太小 |
| `minimax_qss.py:50` 会话列表项字号 | `font-size: 14px` | body-sm: 14px | ✅ 正确 |
| `session_list.py` layout | 无 stretch 分配 | 按钮固定，列表填充 | 按钮可能被挤到不可见 |

#### 根因

`message_bubble.py` 大量使用内联 `setStyleSheet` 绕过 `minimax_qss.py` 中定义的设计令牌。每个开发者在写 bubble 时随意选择字号和间距，没有引用 DESIGN.md。

#### 修复方案

- 将所有硬编码字号替换为 DESIGN.md typography 令牌（body-md: 16px, body-sm: 14px, caption: 13px）
- 将所有间距替换为 spacing 令牌（xs: 8px, sm: 12px, md: 16px）
- 移除无效的硬编码值

---

### P1-2：用户气泡和助手气泡渲染不对称

**文件**: `src/gui/widgets/message_bubble.py:72-100`

#### 根因

| 差异点 | _UserMsg（用户） | _AssistantMsg（助手） |
|--------|-----------------|---------------------|
| 基础 widget | `QLabel + wordWrap` | `QTextEdit + Markdown` |
| 宽度限制 | `setMaximumWidth(480)` 绝对限制 | 无限制（靠 margin 控制） |
| 渲染引擎 | 纯文本 | mistune Markdown → HTML |
| 高度计算 | QLabel 自动（4行后截断） | `_auto_fit` + `documentSizeChanged` 信号 |
| 对齐 | 右对齐 | 左对齐 |

QLabel 和 QTextEdit 的行高算法、文本换行点、padding 表现完全不同，导致用户消息和助手消息视觉上不对称。

#### 修复方案

- 将用户消息也从 QLabel 改为 QTextEdit（支持 Markdown 输入），与助手消息使用同一渲染引擎
- 统一宽度限制逻辑（双方都用相同的 max-width 或百分比）

---

### P1-3：流式渲染滚动时机错误

**文件**: `src/gui/widgets/chat_view.py:37`

```python
QTimer.singleShot(50, self._scroll_to_bottom)
```

#### 根因

- 50ms 太短：`_auto_fit`（`message_bubble.py:35-42`）接在 `documentSizeChanged` 信号上，但该信号的触发时机和 50ms 定时器之间没有保证顺序
- 多事件并发（thought → action → observation 在几百毫秒内连续到达）时，每个事件独立调度 50ms，可能 N+1 个定时器的滚动相互竞争
- 如果一个气泡的 auto-fit 在 50ms 之后才完成，滚动到底部的位置就不包括该气泡的高度

#### 修复方案

- `_auto_fit` 完成后发射自定义信号 `heightUpdated`
- `ChatView` 连接该信号 → 滚动到底部
- 或者改用 `QTimer.singleShot(0, ...)`（下一轮事件循环），配合 QTextEdit 的同步高度计算

---

### P1-4：权限弹窗 UI 粗糙

**文件**: `src/gui/widgets/permission_dialog.py`

#### 问题

- 无 icon/图标指示危险等级
- 按钮文字为"允许"/"拒绝"，不够明确（对比 VSCode：Allow / Deny / Allow for this session）
- 无"记住选择"选项
- QTextEdit 在 setHtml 时代码块无语法高亮

---

### P1-5：历史消息加载的角色映射不完整

**文件**: `src/gui/main_window.py:261-262`

```python
def _role_to_event(role: str) -> str:
    return {"user": "user", "assistant": "answer", "tool": "observation"}.get(role, "answer")
```

"thought" 类型不存在于 DB 中（被存为 assistant），所以实际影响有限。但 fallback 到 "answer" 而不是 "thought" 可能使辅助消息渲染为 Markdown 气泡而非灰色斜体。

---

## P2 — 次要问题

### P2-1：QSS 选择器范围过大

**文件**: `src/gui/styles/minimax_qss.py`

```css
QDialog { background-color: ... }    /* 影响 QMessageBox 等内置对话框 */
QScrollBar:vertical { ... }          /* 影响所有垂直滚动条 */
* { font-family: ... }               /* 与 QFluentWidgets 内部字体冲突 */
```

#### 修复方案

使用 objectName 前缀限定作用域：`#chatView QScrollBar:vertical`, `#permDialog` 等。

---

### P2-2：会话切换时输入栏状态不重置

**文件**: `src/gui/main_window.py:207-230`

引擎运行时切换会话 → `_switch_to_session` 不调用 `_input_bar.setEnabled(True)` → 输入栏永久禁用。

---

### P2-3：私有属性访问

**文件**: `src/gui/main_window.py:256`

```python
if self._session_list._list.count() > 0:
```

应改为 `SessionList` 提供公共属性或方法：

```python
@property
def count(self) -> int:
    return self._list.count()
```

---

### P2-4：ChatView.clear() 延迟删除泄漏

**文件**: `src/gui/widgets/chat_view.py:43`

```python
item.widget().deleteLater()
```

频繁切换会话时，延迟删除的 widget 在 Qt 事件循环中堆积。对于短生命周期的会话切换，应直接 `.delete()` 保证即时回收。

---

### P2-5：ToolCall 折叠状态文本解析脆弱

**文件**: `src/gui/widgets/message_bubble.py:187-189`

```python
self._header.setText(f"▲ {self._header.text()[2:]}")
```

通过 `[2:]` 去掉前缀 "▼ " 或 "▲ "，依赖文本固定宽度 2 字符。应该用内部状态来跟踪展开/折叠。

---

### P2-6：SessionList 新建按钮布局可能被挤压

**文件**: `src/gui/widgets/session_list.py:60-61`

```python
layout.addWidget(self._new_btn)
layout.addWidget(self._list)
```

没有设置 stretch factor，`QPushButton` 可能被 `QListWidget` 挤到看不见。应该：

```python
layout.addWidget(self._new_btn, stretch=0)  # 固定高度按钮
layout.addWidget(self._list, stretch=1)     # 弹性填充列表
```

---

### P2-7：零 GUI 单元测试

`tests/gui/` 目录不存在。以下是必须覆盖的测试范围：

| 测试目标 | 方式 | 优先级 |
|---------|------|--------|
| EventBridge 信号发射 | mock AgentRuntime | P0 |
| MessageBubble 各类型渲染 | 创建 bubble 验证 widget 类型 | P0 |
| CommandParser 命令分发 | 纯函数测试 | P0 |
| PermissionDialog 模态阻塞 | 验证 exec 被调用 | P1 |
| ChatView append/clear | 验证气泡计数 | P1 |
| SessionList CRUD | mock Repository | P1 |
| main_window 事件分发 | mock 所有依赖 | P1 |

---

## 事件管道完整追溯

以下是从引擎到屏幕的完整数据流，标注了每个环节的转换：

```
src/core/react_engine.py  Iter_steps()  yield event
    │
    │ event = {type, iteration, data: {specific fields}}
    │
    ▼
src/runtime/conversation_session.py  run_turn() yield event
    │  同形状透传，不修改 event
    │
    ▼
src/runtime/agent_runtime.py  execute() yield event
    │  同形状透传，不修改 event
    │
    ▼
src/gui/services/event_bridge.py  EventBridge._run_engine()
    │  async for event in runtime.execute(text):
    │  event_received.emit(dict(event))    ← 透传，未修改
    │
    ▼
src/gui/main_window.py  MainWindow._on_event_safe(event)
    │  ★★★ 这里数据被破坏 ★★★
    │  event_type = event.get("type")
    │  data = event.get("data", event)
    │  content = data.get("content", str(data))
    │       ↑ "content" 在 action/observation/answer 中不存在
    │       ↑ 退化为 str(data) = Python dict 字符串
    │
    ▼
src/gui/widgets/chat_view.py  append_event({"type", "content"})
    │
    ▼
src/gui/widgets/message_bubble.py  MessageBubble.create(type, data)
    │  需要正确的结构才能渲染
```

---

## 修复路线图

### 阶段一：P0 紧急修复（约 2 小时）

| # | 问题 | 文件 | 工作量 |
|---|------|------|--------|
| P0-1 | 事件转换 | `main_window.py` | 30 min |
| P0-2 | 气泡样式脱节 | `message_bubble.py` + `minimax_qss.py` | 1 h |
| P0-3 | 权限注入 | `main.py` | 15 min |
| P0 测试 | P0 覆盖测试 | `tests/gui/` | 4 个测试 |

### 阶段二：P1 体验修复（约 3 小时）

| # | 问题 | 文件 | 工作量 |
|---|------|------|--------|
| P1-1 | 设计系统一致性 | 多个 | 1.5 h |
| P1-2 | 气泡渲染对称 | `message_bubble.py` | 30 min |
| P1-3 | 滚动时机 | `chat_view.py` + `message_bubble.py` | 30 min |
| P1-4 | 权限弹窗增强 | `permission_dialog.py` | 30 min |

### 阶段三：P2 质量加固（约 2 小时）

| # | 问题 | 工作量 |
|---|------|--------|
| P2-1 | QSS 选择器范围 | 20 min |
| P2-2/P2-3/P2-4/P2-5/P2-6 | 次要修复 | 30 min |
| 剩余测试 | 补全测试 | 1.5 h |

**总预计：约 7 小时**

---

## 总结

三个 P0 修完 GUI 就能正常使用。核心事件管道断裂（P0-1）是最优先修复项。

建议修复顺序：
1. `main_window.py:_on_event_safe` — 事件转换
2. `main.py` — 权限弹窗注入
3. `message_bubble.py` + `minimax_qss.py` — 气泡样式统一
4. 补 P0 覆盖测试
5. 进入 P1、P2

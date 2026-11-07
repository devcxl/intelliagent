# ADR 0013: 会话模型与选择（每 workspace 多会话 + 启动期选择）

## 状态

已决策，已实施。取代 README 中「TUI 固定续接同一数据库中的 `tui` 会话」的旧行为。

## 背景

TUI 启动时硬编码 `TUI_CONVERSATION_ID = "tui"` + `resume=True`：一个数据库只能承载一段交互式会话，想开新话题必须删除 `intelliagent.db`。存储层的多会话能力已经存在但未被使用——`ensure_conversation(id)` / `latest_leaf_in(id)` 已实现，会话根 entry 不进模型投影，`latest_leaf_in` 只跟随 `message` / `compaction` 两种类型。

同时缺三样东西：会话的可读标识（没有标题）、会话与工作目录的关联（没有 workspace 字段）、会话的枚举能力（没有 `list_conversations`）。

## 决策

### 会话标识与隔离

每个会话是 `entries` 表中一条 `conversation` 类型 entry，id 形如 `tui-{uuid4().hex}` / `headless-{uuid4().hex}`。会话根 payload 记录 `workspace`（启动时的 `Path.cwd().resolve()`）与 `created_at`；会话列表按 `workspace` 过滤，因此**同一数据库可在不同项目目录下各存多段会话**。

### 选择方式：启动期选择 + 新开窗口

| 入口 | 无 flag | `-c` | `-s <id>` |
|---|---|---|---|
| TUI | 新建会话 | 恢复本 workspace 最近创建的会话；无则等同新建 | 打开指定会话；**不存在则启动失败退出 2** |
| headless | 新建会话 | 恢复本 workspace 最近创建的会话 | 打开指定会话；不存在则退出 2 |

`-s` 指向不存在的会话时显式失败而非静默新建：静默新建会让用户以为续上了上下文，实际从零开始，是比报错更糟的失败模式。

**新开窗口新建会话**是首选的多会话用法：另一个进程、另一个 `conversation_id`、共用一个 SQLite；每个进程的 `Engine._messages` 与 `Compactor._tip` 都是进程内状态，天然隔离，无需任何额外机制。

### TUI 内的会话切换

TUI 提供斜杠命令（仅当输入框首字符为 `/` 且尚未出现空格时进入命令模式）：

- `/resume`：弹出会话列表模态（标题 · 相对时间 · id 短前缀），方向键选择 + Enter 确认 + Esc 取消。
- `/new`：新建并切换到一段新会话。

**运行中（run 未收束）执行这两个命令会被拒绝**，并提示先按 `Esc` 中止。切换点因此永远落在 idle 状态，in-flight 工具产出的 `Observation` 不可能被 `Compactor` 落到新会话的链上。自动中止再切换体验更顺，但需要在现有 `_run_worker` / `_run_settled` / `_pending_runner` 三个协同状态之外再叠加一个「待切换」状态，是最容易产生竞态的地方；拒绝提示更诚实，且不锁死后续升级。

### 切换的实现形态

切换会话**不重建 host、不重连 MCP、不改 Engine**：

1. `build_host` / MCP 连接 / LLM 客户端在应用启动时建一次，不再放在 `runner_factory` 内部（原实现每次 factory 调用都重建，实际只被调一次，属于潜在浪费）。
2. 切换 = 用同一个 host 造一个新的 `EngineRuntime`（`conversation_id` 换掉、`resume` 按需），替换 `app._runner`，并清空消息流与 `_tool_panels`。
3. **切换时不调 `runtime.close()`**：`StorageStore.close()` 是终态（`_closed = True` + `engine.dispose()`），而 `EngineRuntime.close()` 会顺手关闭 storage，调用它会让新会话的存储直接失效。旧 runtime 只丢弃引用，应用退出时统一 close。

Engine 的 `_messages` 只活在实例中，换实例即换会话，因此无需给 Engine 增加「重置」入口——那是与 append-only 单会话设计原则相违背的后门。

### 会话标题

标题在**首轮对话完成后**由一次独立的 LLM 单发调用生成（同一 `default_model`，输出上限 64 token，5 秒超时），失败或超时静默回退为「首条 user 消息前 40 字」。

标题落库为 `conversation_title` 类型 entry（append-only）。不写进 conversation 根 payload，因为 `entries` 表挂有拒绝 UPDATE 的触发器，事后改名在 append-only 下不可能；追加新 entry 是唯一合法写法。`latest_leaf_in` 只跟随 `message` / `compaction`，因此新增该 entry 类型不干扰 leaf 查找。

## 被否决的方案

- **运行中直接切换**：in-flight 工具的 `Observation` 会经 `Compactor` 落到新会话链上，污染数据。
- **运行中自动中止再切换**：需在既有 worker 状态机上叠加「待切换」，竞态风险高于收益。
- **会话标题在创建时一次写定、不支持自动生成**：用户明确要求首轮完成后自动生成。
- **标题写进 conversation payload 并原地更新**：被 append-only 触发器拒绝，且破坏记录不可变性。

## 后果

- 删除 `intelliagent.db` 不再是开新话题的唯一方式。
- 会话不 fork：`latest_leaf_in` 在检测到分叉时显式报错，这一保护保留。
- 会话标题生成会给首轮增加一次额外的模型调用（输出上限很小）。

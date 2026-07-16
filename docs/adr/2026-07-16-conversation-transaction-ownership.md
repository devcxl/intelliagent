# ADR：Conversation、Turn 与事务所有权

## 状态

已提议

## 背景

当前 active Conversation 同时存在于 GUI、EventBridge、ConversationService、AgentRuntime 和 ConversationSession。
GUI 直接持有 Repository 和长生命周期 AsyncSession；TaskTools 通过可变 conversation provider 获取上下文。

ConversationSession 没有 turn 串行化和完整取消语义。Repository 自行 commit，Context compaction 传空 source IDs，导致
数据库无法原子替换历史。工具调用和最终回答在流式消费期间逐条落库，取消时可能留下非法 provider 历史。

## 决策

### ConversationApplication 是唯一应用入口

新增 `ConversationApplication`：

- 唯一持有 active ConversationSession。
- 提供 create/open/delete/list/load/submit_turn/cancel_active/close。
- CLI 和 GUI 只依赖该入口和应用 DTO。
- AgentRuntime 只负责装配与资源生命周期，并通过 `runtime.conversations` 暴露应用入口。

ConversationService 改为无状态；删除跨类私有 `_conversation_id` 写入。ConversationSession 绑定不可变 conversation ID。

busy 表示存在 active/queued turn，不是仅存在 idle session。create/open/delete 在 busy 时拒绝；idle session 可关闭并被原子
替换或删除，DB 操作失败时保留原 active session。删除非 active Conversation 不修改 active session。

### 单 Conversation FIFO

ConversationSession 拥有单一队列和 worker。enqueue 在队列锁内分配递增 turn_sequence，该时刻是提交顺序线性化点。

每个已接收 turn 返回 TurnHandle，并恰好产生一个 terminal/TurnOutcome。ReactEngine 通过 event sink 发 thought/action/observation
并返回 EngineResult；ConversationSession 在 persistence 完成后独占 terminal 构造权。

### cancel 与 terminal 共用线性化锁

cancel 在同一队列锁内进入 CANCELLING、detach active、清空 queued、递增 generation 并创建 Session-owned cleanup task：

- queued turn 直接 cancelled，不落 Message。
- 释放队列锁后，cleanup task 才取消并等待 turn-owned runner/request/tool task；禁止持锁等待 runner。
- CANCELLING 时新提交返回 `RUN_CANCELLING`。
- active/queued/cancelling 时 create/open/delete 返回 `CONVERSATION_BUSY`。
- runner、LLM 和 ToolExecutor 共用 CancellationToken；取消后停止消费 Engine，Callback 返回后和 Registry.invoke 前再次检查，
  防止取消线性化点后启动新工具。
- late result 通过 turn ID/generation guard 丢弃。
- active user message可以保留；assistant/tool 业务消息不提交。
- 已完成的文件、shell、MCP 等外部副作用不回滚。

cleanup 完成后重新获取队列锁，通过幂等 finish-once 完成 active cancelled terminal。重复 cancel 等待同一个 cleanup task。

### Service 拥有事务

- 目标状态下 Repository 只 add/delete/execute/flush，不 commit/rollback。
- ConversationService、TaskService、AgentTeamService 各自创建短 session/transaction。
- 事务不得跨越 LLM、工具、权限弹窗或 UI 交互。
- TaskService 在 P1 引入，保证批量 Task 原子性。
- TaskService 的 get/update/finish 同时约束 task ID 和 conversation ID，parent task 也必须属于同一 Conversation。

迁移按 Conversation、Task、Agent Team 垂直切片执行：先增加 flush-only API，再在同一切片迁移 Service/Tool 调用方，最后删除
共享 commit API。禁止先全局移除 BaseRepository commit，避免未迁移用例静默 rollback。

### Turn success-time persistence

- active turn 启动时单独提交 user message，并以真实 message ID/message_sequence 加入 ContextManager。
- assistant/tool plan message 拥有唯一 plan_message_id 和预分配 message_sequence。
- success terminal 前一个事务提交 plan。
- error/cancelled 丢弃 plan并使 Engine 失效。
- Message 增加 per-conversation message_sequence 唯一约束，以及 is_summary/compression_count 字段。
- DB message 通过 role 白名单转换为 provider message。

### Context compaction 原子替换

保留 ADR 0001 的 75% 阈值、确定性 summary、稳定 instruction prefix 和 user-role summary。

ContextSummary 同时记录真实 source message IDs 和被摘要吸收的 plan_message_ids。连续 compaction 合并两组身份。success-time
事务只插入最终 summary 之后未被吸收的 plan messages；任何失败整体 rollback。

发生 compaction 的 success、普通 error、cancelled 或 DB failure 都使 Engine 失效，下一 turn 从 DB 重载。summary 通过
is_summary/compression_count 识别，不依赖内容前缀。

### GUI 通过应用入口访问数据

- `src/gui` 禁止 import DB、ORM、Repository 和 SQLAlchemy。
- SessionList 是纯展示组件，只发 intent。
- MainWindow 使用 DTO 渲染。
- EventBridge 消费 TurnHandle 和唯一 terminal。
- GUI shutdown 必须 await Runtime 清理后退出 qasync loop。
- 顶层 GUI coroutine 必须被 qasync loop await；closeEvent 先发 shutdown intent，完成后才允许 app.quit。
- PermissionDialog 使用 open + Future/finished signal，turn cancel 时关闭 dialog，禁止用同步 exec 阻塞取消。

保留 PyQt5、qasync、mistune 和现有核心 GUI 流程。

## 备选方案

### AgentRuntime 直接承担应用入口

少一个类，但 Runtime 会再次同时承担 composition、生命周期、CRUD、active 状态和调度，重现 ADR 0006 已识别的问题，
因此不采用。

### 每个 Conversation 一个常驻 actor

允许多会话后台并行，但接近 Agent Worker/Bus，增加跨 session 调度和资源所有权，超出单 active Conversation 范围，
因此不采用。

### 逐条持久化 assistant/tool 消息

崩溃时保留更多过程，但取消可能留下未配对 tool-call 历史。相比之下，success-time persistence plan 更容易保证协议合法性和
唯一终态，因此不采用逐条提交。

## 后果

正面：

- active Conversation 和 TurnContext 只有一个权威来源。
- FIFO、取消、删除和 terminal 具有可测试线性化语义。
- GUI/CLI 共用应用行为，GUI 不再泄漏 DB。
- compaction、批量 Task 和多实体用例可原子 rollback。
- 重启后 provider message 结构合法且上下文一致。

负面：

- 需要新增 ConversationApplication、TurnHandle 和 per-conversation queue。
- Message schema 增加 message_sequence/is_summary/compression_count，开发库需要重建。
- 取消前已经完成的外部副作用无法统一回滚。
- success-time persistence 会在 turn 成功前暂存 assistant/tool 消息。

## 与现有 ADR 的关系

- 补充 ADR 0001 的持久化 source IDs 和原子替换，不改变摘要策略。
- 部分取代 ADR 0005 中可变 conversation provider 的注入方式；保留 Agent Team 三层结构。
- 延续 ADR 0006 的 SRP/DI 和按表 Repository；明确 Service 拥有事务。
- 部分取代 ADR 0007 的“GUI 零修改 Core/Runtime/DB”、Core AsyncGenerator 直连、同步 PermissionDialog.exec 和 QFluentWidgets
  选择；保留 PyQt5、qasync、mistune 和事件内容。

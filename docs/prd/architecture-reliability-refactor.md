# PRD: IntelliAgent 架构可靠性修复

- **状态**: Approved
- **创建日期**: 2026-07-16
- **决策者**: 仓库维护者
- **来源**: `docs/architecture-report.md`（审查基线 `main@79509b3`）
- **交付方式**: 一个 Parent Issue，按 P0 / P1 / P2 拆分为独立可验收批次

## 1. 背景与动机

IntelliAgent 的目标是成为适合维护、教学和招聘展示的 coding-agent skeleton。当前目录已经按
`core`、`runtime`、`tools`、`db`、`llm`、`gui` 等职责拆分，但安全策略、会话状态、数据库事务和
provider 契约仍由多个模块共同拥有。

架构审查确认了以下系统性问题：

- MCP 工具被默认规则整体放行，敏感路径 deny 可被工具名前缀规则覆盖。
- GUI、Runtime、ConversationService 和 ConversationSession 同时保存当前会话状态。
- Context compaction 只改变内存状态，数据库重启后会重新加载原始历史和摘要。
- Repository 自行提交事务，应用服务无法保证跨操作原子性。
- SQLite 外键未启用，孤儿 Message / Task 可以被写入。
- 工具失败、权限拒绝和 Engine error 在事件链路中可能被报告为成功。
- Core 直接理解 OpenAI tool-call / usage shape，provider seam 不真实。
- `tools`、`config`、`types`、`skills` 中存在装配职责或类型归属错误。
- 当前测试数量充足，但缺少确定性的完整 Runtime 集成门禁，且资源泄漏 warnings 不会使 CI 失败。

如果不修复，这些问题会继续让新增 provider、前端、工具或持久化行为同时修改多个包，并增加安全绕过、
跨会话写入、恢复失败和文档继续漂移的概率。

## 2. 目标用户与业务价值

### 2.1 目标用户

- IntelliAgent 仓库维护者。
- 通过该项目学习 coding agent 架构的开发者。
- 使用 CLI 或 PyQt5 GUI 运行本地 coding agent 的用户。

### 2.2 业务价值

- 让每个关键运行时状态和事务只有一个明确所有者。
- 让工具权限、执行结果和终止状态可审计、可测试、不可静默降级。
- 让 Core 能在不加载 GUI、DB、MCP、Skills 和具体 provider SDK 的情况下独立理解和测试。
- 让新增 adapter 时通过稳定 seam 接入，而不是修改 ReAct loop。
- 让 CI 能阻止资源泄漏、依赖方向回退和跨层行为回归。

## 3. 成功指标

- 所有 P0 / P1 / P2 验收标准通过，并由仓库维护者最终确认。
- `uv run pytest --tb=short`、`uv run ruff check .`、`uv run ruff format --check .` 全部通过。
- 测试过程不再产生 `PytestUnhandledThreadExceptionWarning`、未等待 coroutine 或资源泄漏 warning。
- CI 将上述资源/线程 warning 视为失败。
- 新增确定性的 fake-LLM Runtime 集成测试，不依赖真实 API key 或网络。
- 新增依赖边界测试，阻止 `core -> adapter`、`gui -> db`、`config -> network`、`tools -> runtime assembly` 回退。
- CLI 和 GUI 的现有核心流程保持可用：创建/恢复/删除会话、执行 turn、工具调用、权限确认、历史恢复。

## 4. 范围

### 4.1 P0：安全与事实正确性

| ID | 需求 | 完成条件 |
|----|------|----------|
| P0-01 | MCP 缺省权限改为 `ask` | MCP 全局 fallback 为 `ask`；更具体的 deny 和 PathPolicy 硬边界优先；用户规则仍可显式覆盖默认规则 |
| P0-02 | 工具执行 fail closed | 无 PermissionEngine 时始终拒绝；`ask` 且无 Callback 时返回 `no-callback`；`allow` 不需要 Callback |
| P0-03 | 统一路径边界语义 | PermissionEngine 和文件工具复用同一 PathPolicy；路径越界是用户规则不可覆盖的硬边界 |
| P0-04 | 启用 SQLite 外键 | 每条 SQLite 连接均为 `PRAGMA foreign_keys=ON`，孤儿 Message / Task 写入失败 |
| P0-05 | 保留工具错误状态 | Core-owned ToolResult 贯穿 Registry、ToolExecutor、Engine Event、CLI/GUI，不得把失败标记为成功 |
| P0-06 | 修复 Runtime 资源泄漏 | Runtime、DB、MCP、LLM client 和 shell subprocess 在正常退出、异常和取消后都完成本地清理 |
| P0-07 | CI 阻止线程/资源 warning | 当前 aiosqlite worker warning 必须消失，相关 warning 在 pytest/CI 中升级为失败 |

### 4.2 P1：会话、事务与生命周期所有权

| ID | 需求 | 完成条件 |
|----|------|----------|
| P1-01 | 建立统一 Conversation 应用入口 | CLI/GUI 通过应用服务完成 create/open/delete/list/load；active/queued turn 存在时 create/open/delete 均返回 `CONVERSATION_BUSY` |
| P1-02 | 当前会话只有一个所有者 | 删除跨类写私有 `_conversation_id`；每个 turn 使用不可变、显式的 conversation context |
| P1-03 | 同一会话的 turn 按 FIFO 排队 | 在同一队列锁内为已接收 turn 分配递增序号，并按序号串行执行 |
| P1-04 | 取消会清空当前会话队列 | cancel 在队列锁内线性化；active 和 queued turn 均返回 `cancelled`，CANCELLING 期间新提交返回 `RUN_CANCELLING` |
| P1-05 | 取消提供本地强保证 | 关闭 turn-owned task/request/stream，丢弃 late result，不保存 assistant/tool 业务结果；已完成的工具副作用不保证回滚 |
| P1-06 | Context compaction 原子持久化 | 被压缩原始消息与 summary 在同一事务内完成替换，重启后只恢复 summary 和未压缩消息 |
| P1-07 | Service 拥有事务边界 | Repository 不自行 commit；ConversationService、TaskService、AgentTeamService 分别拥有短事务和 rollback |
| P1-08 | 持久化消息显式转换 | DB metadata 不得直接发送给 LLM；按 message role 白名单生成 provider message |
| P1-09 | GUI 不共享长生命周期 AsyncSession | 每个应用用例使用独立短 session；Widget 不 import ORM/Repository |
| P1-10 | 终态在事件链中唯一且可信 | 每个 turn 只产生一个 `terminal` 事件，携带 success/error/cancelled TurnOutcome |
| P1-11 | 增加确定性 Runtime 集成测试 | 使用 fake LLM + 真实 Runtime/DB/Permission/ToolRegistry 覆盖权限、工具、持久化、恢复和取消 |

### 4.3 P2：Core ports、包归属与架构门禁

| ID | 需求 | 完成条件 |
|----|------|----------|
| P2-01 | 引入最小 provider-neutral DTO | `LLMResponse`、`ToolCall`、`TokenUsage`、`ToolSpec` 由 Core ports 所有，Core 不读取 OpenAI SDK 对象属性 |
| P2-02 | 保持单一 provider 实现 | 本次只适配现有 OpenAI-compatible client，不新增第二个 provider |
| P2-03 | Runtime 成为唯一 composition root | `ToolRegistryFactory` 或等价装配逻辑移入 `runtime`，tools 包只保留 schema、registry 和 adapter |
| P2-04 | 解除 tools / skills 循环 | `SkillTool` 归入 tools；Skills 包只负责 model、loader、registry |
| P2-05 | Task 业务移出 Tool adapter | P1 引入最小 TaskService；P2 确保 TaskTools/AgentTeamTools 只解析参数、调用 Service、映射 ToolResult，不再 import DB/ORM |
| P2-06 | Config 恢复为 typed settings | config 包不执行网络请求或用户目录写入；Provider catalog 归入 LLM adapter/runtime |
| P2-07 | Provider metadata 启动语义明确 | 显式 context limit 或 24 小时内有效缓存可离线启动；否则远程获取总 deadline 为 3 秒，失败则启动失败 |
| P2-08 | MCP schema 不被压平 | ToolSpec 保存完整 JSON Schema，保留嵌套对象、数组、enum、oneOf/anyOf 等约束 |
| P2-09 | Registry 注册有所有权 | 重名注册默认失败；动态 MCP 工具按 owner/token 注销，不会删除其他来源的同名工具 |
| P2-10 | 类型按消费者归属 | LLM port 归 Core；provider metadata 归 LLM adapter；移除无消费者的通用 MemoryProtocol/types 收容包 |
| P2-11 | Permission 包边界明确 | Permission policy 可保留为 core-domain package；CliCallback 移入 CLI；配置到实例的装配归 Runtime |
| P2-12 | 自动检查依赖方向 | 按 6.5 节列出的精确 import 前缀建立自动测试，不使用含义模糊的 `core -> adapter` 规则 |
| P2-13 | 文档与实现同步 | 更新 CONTEXT、README、GUI PRD/Spec、相关 ADR、intelliagent.json.example 和其引用的 JSON Schema |
| P2-14 | 删除预留但未使用的 Memory 结构 | 开发库允许重建，不为尚未立项的 Memory 功能保留 Protocol 或表结构 |

## 5. 用户故事

### US-01：安全执行工具

> 作为本地 coding agent 用户，我希望任何未明确授权的 MCP 或副作用工具都不能静默执行，以便保护工作区、凭据和外部系统。

**验收标准：**

- 未配置 MCP 规则时，MCP 工具得到 `ask` 决策。
- 默认配置下，`mcp_filesystem_read(path=".env")` 不得得到 `allow`；维护者显式规则可以按 last-match-wins 覆盖。
- 无 PermissionEngine 时工具调用次数为 0；`ask` 且无 Callback 时调用次数也为 0；`allow` 不需要 Callback。
- deny/reject/no-callback/error 在 Event、CLI 和 GUI 中保持失败状态。

### US-02：可靠地管理多轮会话

> 作为 CLI/GUI 用户，我希望同一会话中的多个输入按提交顺序执行，切换、删除和取消不会把消息或任务写入错误会话。

**验收标准：**

- 同一 Conversation 的并发输入按 FIFO 顺序完成。
- 每个工具调用使用 turn 创建时固定的 conversation ID。
- Task get/update/finish 必须同时约束 task ID 和固定的 conversation ID，parent task 必须属于同一 Conversation。
- 删除或切换会话通过统一应用服务完成，并验证目标存在。
- Conversation 有 active/queued turn 时 create/open/delete 均返回 `CONVERSATION_BUSY`，不触发隐式取消或排队切换。
- cancel 后每个已接收 turn 恰好返回一个 `cancelled` outcome，不保存 assistant/tool 业务结果。
- CANCELLING 期间的新提交立即返回 `RUN_CANCELLING`，本地资源清理完成后才重新接受 turn。

### US-03：重启后获得一致上下文

> 作为长期运行 Agent 的用户，我希望 compaction 后重启不会重新加载已压缩历史或产生重复 summary。

**验收标准：**

- compaction 结果携带明确的 source message IDs。
- 删除原消息和写入 summary 处于同一事务。
- summary 写入失败时原消息不会丢失。
- 重启后只加载 summary、稳定 instruction prefix 和未压缩消息。

### US-04：通过稳定接口扩展系统

> 作为维护者，我希望新增 provider、tool 或前端时只实现对应 adapter，而不修改 ReAct loop。

**验收标准：**

- Core 只接收 provider-neutral DTO 和 ports。
- Runtime 创建具体 provider、tools、skills、permissions 和 persistence adapters。
- GUI 只依赖应用层接口。
- 自动依赖测试能在非法 import 出现时失败。

### US-05：在 CI 中发现架构回退

> 作为维护者，我希望 CI 能发现资源泄漏、错误状态丢失、事务破坏和依赖方向回退，以便避免“测试全绿但行为错误”。

**验收标准：**

- fake-LLM Runtime 集成测试不依赖网络或真实 API key。
- pytest 中线程异常、未等待 coroutine 和资源泄漏 warning 会导致失败。
- 生产 SQLite engine 测试验证 FK、事务 rollback 和重启恢复。
- CLI 至少有 `--help`、EOF、执行异常和 shutdown smoke。
- GUI 覆盖创建、恢复、删除、执行 turn、权限确认、历史恢复和错误终态，确保现有 PyQt5 GUI 不被删除或降级。

## 6. 详细验收标准

### 6.1 安全与路径

- [ ] 默认权限规则不包含 MCP 全局 allow。
- [ ] 用户显式规则仍遵循 last-match-wins，可明确覆盖默认 `.env*` / MCP 规则。
- [ ] PathPolicy 在用户规则前执行；工作区外且不在 external directories 的已声明本地路径始终 deny，用户规则不可覆盖。
- [ ] MCP server 内部或未声明资源语义不在本地路径沙箱保证范围内，因此未配置规则时始终 `ask`。
- [ ] 无 PermissionEngine 时所有工具拒绝；`ask + no callback` 返回 `no-callback`；`allow` 不调用 Callback；`deny` 不调用 Callback。
- [ ] fail-closed 测试同时覆盖非法 arguments、未知工具和工具函数调用次数。
- [ ] PathPolicy 参数化测试覆盖第一个、中间和最后一个 external directory。
- [ ] 文件工具和 PermissionEngine 对同一路径给出一致边界判断。

### 6.2 数据与事务

- [ ] 生产 `create_engine()` 创建的每条 SQLite 连接均返回 `PRAGMA foreign_keys=1`。
- [ ] 向不存在的 Conversation 写 Message/Task 会失败。
- [ ] Repository 不调用 `commit()`；应用服务显式提交或回滚。
- [ ] 批量 Task 中途失败不会留下部分记录。
- [ ] Task get/update/finish 按 `task_id + conversation_id` 查询；禁止跨 Conversation 修改、完成任务或引用 parent task。
- [ ] compaction 删除与 summary 写入具备 rollback 测试。
- [ ] 当前项目为 0.1 开发阶段，允许删除并重建本地 SQLite，不要求 legacy migration。

### 6.3 会话与取消

- [ ] Active Conversation 只有一个公开所有者，不存在跨类私有字段写入。
- [ ] enqueue 在每个 Conversation 的队列锁内分配递增序号，该时刻定义为 FIFO 提交顺序的线性化点。
- [ ] FIFO 队列测试至少并发提交 3 个 turn，并断言执行、Event 和持久化顺序与序号一致。
- [ ] cancel 获取同一队列锁的时刻定义为取消线性化点；active 和 queued turn 各自产生且只产生一个 `cancelled` outcome。
- [ ] cancelled turn 不保存 assistant/tool 业务结果；允许单独记录取消审计状态，late LLM/MCP/tool 结果必须丢弃。
- [ ] 取消前已经完成的文件、shell、MCP 或其他外部工具副作用不保证回滚；本次不增加补偿事务。
- [ ] CANCELLING 状态的新提交立即返回 `RUN_CANCELLING`，不得进入旧队列或新队列。
- [ ] active/queued turn 存在时删除 Conversation 返回 `CONVERSATION_BUSY`，不删除 DB 数据且不产生后续业务 Event。
- [ ] active/queued turn 存在时 create/open 同样返回 `CONVERSATION_BUSY`；idle session 可被安全关闭并替换。
- [ ] shell subprocess 被 terminate/kill 后完成 `wait()`，无遗留进程。
- [ ] 只取消 turn-owned request/task/stream，不关闭共享 Runtime client；本地关闭后的 late result 不产生业务 Event 或 DB 写入。
- [ ] LLM 返回后、工具开始前再次检查取消令牌；取消线性化点后不得启动新的 handler。
- [ ] 远端实际停止和计费终止只作为 best-effort，不作为完成条件。

### 6.4 事件与 UI

- [ ] ToolResult 至少表达 success/error/denied/rejected/no-callback/cancelled。
- [ ] 每个 observation 保留 ToolResult 的状态和错误码。
- [ ] Engine error event 导致 TurnOutcome 失败。
- [ ] action event 在工具开始执行前发出，observation 在执行完成后发出。
- [ ] 每个已接收 turn 恰好产生一个 `terminal` 事件；移除 answer/error 双终态推断。
- [ ] GUI 不 import `src.db`，SessionList/MainWindow 不持有 Repository。
- [ ] CLI 和 GUI 对失败、取消、权限拒绝显示可区分的终态。

### 6.5 Ports 与包边界

- [ ] Core 源码中不出现 OpenAI SDK tool-call/usage 属性访问。
- [ ] Core-owned `ToolSpec` 保存名称、来源、已声明本地路径字段和完整参数 JSON Schema；owner 是 Registry 注册元数据，不进入 ToolSpec。
- [ ] Core-owned `CanonicalMessage` 定义 SDK-neutral 的 user/assistant/tool 消息形状，LLM adapter 负责转换为 provider wire format。
- [ ] ToolRegistry 使用完整 ToolSpec，不以 OpenAI 命名公共接口。
- [ ] `src/tools/` 不创建 DatabaseRuntime、Service 或其他 Runtime graph。
- [ ] `src/config/` 不 import `urllib` 或执行缓存文件写入。
- [ ] tools / skills 不再形成 package-level cycle。
- [ ] 通用 `src/types/` 不再作为跨域类型收容包。
- [ ] `src/core` 禁止 import `src.db`、`src.tools`、`src.skills`、`src.llm`、`src.mcp`、`src.runtime`、`src.gui`、`src.cli`、`src.config`、`src.services`；允许依赖被声明为 core-domain 的 `src.permission`。
- [ ] `src/gui` 禁止 import `src.db`、SQLAlchemy ORM 和 Repository。
- [ ] `src/config` 禁止 import/调用网络客户端和执行用户目录缓存写入。
- [ ] `src/tools` 禁止 import `src.runtime`、`src.db` 和 SQLAlchemy，也不得创建 Service/Runtime graph。

### 6.6 Provider metadata

- [ ] 解析优先级固定为：显式配置覆盖 > 有效缓存 > 远程获取。
- [ ] 缓存 key 为 `provider_id/effective_model_id`，目标记录必须包含正整数 context limit，格式解析失败视为无效。
- [ ] 缓存文件修改时间不超过 24 小时才视为有效；过期缓存不允许离线启动。
- [ ] 配置显式提供 context limit 或有效缓存存在时不访问网络。
- [ ] 配置和缓存都不可用时，DNS、连接和响应读取共用 3 秒 wall-clock 总 deadline，不自动重试。
- [ ] 上述远程请求失败时，Runtime 启动失败并输出可操作诊断。
- [ ] 成功获取的缓存使用临时文件 + 原子替换写入。
- [ ] 单元测试通过 fake transport 覆盖，不访问 models.dev。
- [ ] 模型引用兼容测试覆盖有/无 provider 前缀、零/单/多 enabled provider、disabled provider、`ModelOverride.id` 和 `small_model`。
- [ ] 显式 limit 按配置 model key 查询；cache、remote 和 SDK 按非空 `ModelOverride.id` 或 model key 形成的 effective model ID 查询。
- [ ] MCP stdio/HTTP 配置的现有外部 JSON 结构保持不变。

### 6.7 质量门禁

- [ ] 全量 pytest、Ruff、format check 通过。
- [ ] CI 至少将 `PytestUnhandledThreadExceptionWarning`、`PytestUnraisableExceptionWarning`、`ResourceWarning` 和表示 coroutine 未等待的 `RuntimeWarning` 视为失败。
- [ ] deterministic Runtime 集成测试覆盖 MCP/fail-closed、路径、SQLite FK、错误终态、FIFO、cancel 清队列、compaction rollback/restart、唯一 TurnOutcome 和 shutdown 零 warning。
- [ ] import-boundary 测试覆盖 P2 依赖规则。
- [ ] CI 使用 `dev + gui` extras 和 `QT_QPA_PLATFORM=offscreen` 运行 GUI 测试；核心 GUI 用例不得 skip。
- [ ] CONTEXT、README、`docs/prd/pyqt5-gui-extension.md`、`docs/dev/specs/pyqt5-gui-extension.md` 和相关 ADR 与实现一致。
- [ ] `intelliagent.json.example` 可被 UnifiedConfig 加载，且其 `$schema` 指向仓库内可解析的 schema。

## 7. 技术约束

- Python 3.11+，类型标注全覆盖。
- 保留 SQLAlchemy 2.x、aiosqlite、PyQt5、qasync、OpenAI-compatible client 和现有配置格式。
- 允许将 `httpx` 声明为直接依赖，用于可取消的异步 Provider metadata 请求和 3 秒总 deadline。
- 不在本次引入完整 Clean Architecture 框架或大量 Repository Protocol / Mapper。
- 优先使用标准库 AST 测试依赖方向，避免仅为 import boundary 增加运行时依赖。
- 测试不得调用真实 LLM、MCP server、models.dev 或其他网络服务。
- GUI 和 CLI 必须共用同一应用层行为，不各自复制会话规则。
- 现有开发数据库允许重建，不新增 migration 框架。
- Provider metadata 缓存有效期为 24 小时；远程获取整个流程的 wall-clock deadline 为 3 秒。
- 单进程、本地用户场景；不新增跨进程调度、QPS 或分布式一致性要求。
- 0.1 阶段不承诺内部 Python import/API 向后兼容；CLI、GUI 和现有 `intelliagent.json` 外部结构是兼容面。
- 内部 API 变更必须在同一实施节点迁移全部仓内调用方和测试，不增加长期兼容 wrapper。

## 8. Out of Scope

- 新增 Anthropic、Gemini、DeepSeek 或其他 provider adapter。
- 实现 Memory、AgentMemory、长期记忆检索或持久化能力。
- 实现 Web/API、移动端或新的调用入口。
- 实现 Agent Worker / Agent Bus、多进程 Agent 调度或消息队列。
- 实现深色主题、恢复 QFluentWidgets 或重新设计 GUI 视觉样式。
- 删除、替换或降级现有 PyQt5 GUI。
- 为现有 SQLite 数据提供 Alembic 或自定义无损迁移。
- 保证远程 LLM/MCP 服务端确认取消或停止计费。
- 引入完整 Clean Architecture、DDD entity/mapper 或插件框架。
- 新插件机制、无关的新工具/入口或其他新产品能力。
- 性能专项优化、虚拟滚动或流式 token UI。
- Release、版本发布和包分发。

详细排除项同步记录在 `docs/dev/out-of-scope.md`。

## 9. 依赖与交付顺序

1. P0：先建立失败测试，修安全、外键、路径、错误状态和资源清理。
2. P1：在 P0 契约稳定后，收口 Conversation、事务、队列和 GUI 边界。
3. P2：在行为稳定后迁移 ports、装配与包归属，并启用依赖门禁。
4. 每个批次必须可独立 review 和回滚，禁止一次性全仓重命名。

## 10. 风险

| 风险 | 缓解措施 |
|------|----------|
| 安全修复改变工具默认行为 | 用明确错误码和权限集成测试固定 fail-closed 语义 |
| Repository 去 commit 造成遗漏提交 | 先增加事务契约测试，再迁移每个应用用例 |
| GUI 会话收口引入交互回归 | 保留 GUI 行为测试，先提供应用服务再替换 Widget 依赖 |
| FIFO 队列与取消语义复杂 | 单会话单 worker，不引入跨进程队列；状态机用确定性测试覆盖 |
| Core DTO 迁移影响大量测试 fake | 先建立 DTO adapter，再逐个替换，不提供长期双轨兼容层 |
| 开发库重建导致本地数据丢失 | 在变更说明中明确提示备份/删除开发数据库 |

## 11. Open Questions

无阻塞性产品问题。技术设计已选择 `ConversationApplication`、Core-owned ports、单会话 FIFO 状态机和
`ProviderCatalog`；具体私有 helper 命名不影响需求验收。

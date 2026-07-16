# IntelliAgent 架构审查报告

- **审查基线**: `main@79509b3`
- **审查日期**: 2026-07-16
- **历史样本**: 19 个 merged PR、26 个 GitHub Issue
- **代码规模**: 87 个生产 Python 文件 / 7,391 行；47 个测试文件 / 5,994 行
- **关联 PRD**: `docs/prd/architecture-reliability-refactor.md`

## 1. 结论

IntelliAgent 不是普遍“文件拆得太细”。主要问题是安全策略、会话状态、事务和跨层 DTO 没有唯一所有者。
目录在形式上已经分层，但关键行为仍跨越 Core、Runtime、Tools、GUI、Services 和 DB，已产生可复现的授权绕过、
会话漂移、压缩持久化失效和错误状态丢失。

整改应按以下顺序进行：

1. P0：修复安全与事实错误。
2. P1：收口会话、事务、取消和 GUI 生命周期。
3. P2：整理 Core ports、包归属和自动依赖规则。

不应先做全仓目录重命名或机械合并小文件。

## 2. 发现总表

| 级别 | 发现 | 主要证据 | 批次 |
|------|------|----------|------|
| Critical | MCP 默认授权覆盖敏感路径默认规则 | `src/permission/engine.py:17-40` | P0 |
| High | 当前会话状态存在多个所有者 | `src/runtime/agent_runtime.py:79-105`、`src/gui/main_window.py:243-351` | P1 |
| High | 同一 Conversation 缺少 turn 串行化，取消不等待收尾 | `src/runtime/conversation_session.py:37-117`、`src/gui/services/event_bridge.py:39-74` | P1 |
| High | Context compaction 永远不删除已压缩消息 | `src/core/react_engine.py:133-142`、`src/services/conversation_service.py:147-161` | P1 |
| High | Repository 自行 commit，Service 无法拥有事务 | `src/db/repositories/_utils.py:23-26`、`src/db/repositories/message.py:22-27` | P1 |
| High | SQLite 外键未启用 | `src/db/engine.py:47-82` | P0 |
| High | 工具失败和 Engine error 被报告为成功 | `src/core/events.py:35-54`、`src/gui/services/event_bridge.py:88-102` | P0 |
| High | Core 使用 OpenAI wire shape | `src/core/react_engine.py:21-40,191-204`、`src/llm/llm_client.py:102-114` | P2 |
| High | `ToolRegistryFactory` 在 Tools 包执行 Runtime assembly | `src/tools/registry.py:117-205` | P2 |
| High | GUI 绕过 Service 并共享长生命周期 AsyncSession | `src/gui/main.py:48-69` | P1 |
| Medium | Config getter 同步联网并写用户目录 | `src/config/unified_config.py:84-104`、`src/config/provider_registry.py:46-56` | P2 |
| Medium | 路径策略重复且第二个 external directory 被拒绝 | `src/utils/path_policy.py:47-59`、`src/utils/path_utils.py:47-67` | P0 |
| Medium | `types` 成为无所有权收容包 | `src/types/llm.py`、`src/types/provider.py`、`src/types/memory.py` | P2 |
| Medium | 真实 Runtime 集成门禁缺失，E2E 默认跳过且接口过期 | `tests/integration/test_react_engine_e2e.py:24-34,129-151` | P1 |
| Medium | CI 存在，但后台线程/资源 warnings 不会导致失败 | `.github/workflows/ci.yml:53-56`、`pytest.ini:1-7` | P0 |

## 3. 安全边界

### 3.1 MCP 默认授权绕过

`PermissionEngine` 采用 last-match-wins。默认规则中 `.env* -> deny` 位于 `mcp * -> allow` 之前，
而 `_match_rule()` 会把 `mcp *` 压缩为 `mcp*` 匹配工具名。因此在默认配置下，
`mcp_filesystem_read(path=".env")` 最终得到 `allow`。

**影响：**

- 任何 MCP server 暴露的读写、命令、数据库或部署工具都被同一前缀整体信任。
- PermissionEngine 只识别顶层 `path` 参数，无法识别 `file_path`、URI 或嵌套资源描述。
- ToolDef 没有来源和资源参数元数据，权限层只能按名称猜能力。

**整改方向：**

- MCP 默认回落到 `ask`，用户显式规则仍可按 last-match-wins 覆盖。
- PathPolicy 作为已声明本地路径的硬边界先于用户规则执行；用户规则不能放行工作区外且不在白名单的路径。
- 缺少 PermissionEngine 时 fail closed；仅 `ask + no callback` 返回 `no-callback`。
- ToolSpec 声明来源、完整 JSON Schema 和可直接验证的本地路径参数；不引入没有消费者的通用 risk 字段。
- ToolExecutor 成为唯一授权入口；文件工具复用同一 PathPolicy 做 defense-in-depth。

### 3.2 路径策略重复并漂移

`path_utils.py` 会逐个检查 external directories；`path_policy.py` 把 `try/except` 包在整个循环外，第一个目录不匹配时
就退出循环。实测目标位于第二个白名单目录时仍返回拒绝。

**整改方向：**保留一个 PathPolicy，实现 workspace、external directories 和相对路径的统一语义，并用参数化测试覆盖
第一个、中间和最后一个白名单目录。

## 4. 会话与生命周期

### 4.1 当前会话存在多个所有者

当前会话 ID 同时存在于：

- `MainWindow._current_conv_id`
- `SessionList._current_id`
- `EventBridge._pending_session_id`
- `ConversationService._conversation_id`
- `AgentRuntime._session` / `ConversationSession.conversation_id`

`AgentRuntime.switch_session()` 还直接写 `ConversationService._conversation_id` 私有字段。TaskTools 在执行时通过闭包读取这个
可变值，而 ConversationSession 固定持有自己的 ID。会话 A 运行中切换到 B 时，聊天消息和 Task 可能写入不同会话。

### 4.2 GUI 绕过应用层

`src/gui/main.py:48-69` 在应用启动时创建一个 AsyncSession，并将 Repository 传给 MainWindow 和 SessionList。
Widget 直接创建、删除和读取 Conversation；`session_deleted` 信号没有接入 MainWindow 状态清理。

共享 Session 还可能被 QTimer 回调、点击处理和 `_async_guard` 启动的异步任务重叠使用。

### 4.3 Turn 串行化和取消不完整

ConversationSession 只有 Engine 初始化锁，没有 turn lock。EventBridge 调用 `task.cancel()` 后立即丢弃引用，不等待 shell、
DB、LLM/MCP transport 完成收尾。assistant tool call 可能已落库，而 tool result 尚未落库，恢复时形成非法 provider 历史。

**整改方向：**

- 建立统一 Conversation 应用入口，GUI 不再 import `src.db`。
- 一个组件拥有 active conversation；每个 turn 使用不可变 TurnContext。
- 同一会话按 FIFO 队列执行。
- cancel 在队列锁内线性化：active 和 queued turn 得到 cancelled outcome，业务结果不落库，late result 被丢弃。
- CANCELLING 期间新提交返回 `RUN_CANCELLING`。
- 只取消 turn-owned task/request/stream，不关闭共享 Runtime client。

## 5. 持久化与事件契约

### 5.1 Context compaction 持久化失效

`ReactEngine._maybe_compact_context()` 固定调用 `compact_callback([], summary.content)`。ConversationService 因此不会删除任何
原消息，只会追加 summary。重启后重新加载“原历史 + summary”，压缩收益消失并产生重复上下文。

Repository 的 delete 和 save 各自 commit，即使未来传入 IDs，也无法保证“删除原消息 + 写 summary”原子完成。

### 5.2 事务所有权错误

BaseRepository.save、ConversationRepository.update/delete、MessageRepository.delete_by_ids 等方法自行 commit。
因此批量 Task、compaction 和多实体用例无法统一 rollback，中途失败会留下部分状态。

### 5.3 错误状态在事件链中丢失

ToolRegistry 把异常转成普通 JSON 字符串，ToolExecutor 随后使用默认 `status="success"`，observation_event 再次硬编码
success。Engine 捕获异常后只 yield error event，EventBridge 消费完成后仍发 `success=True`。

**整改方向：**

- CompactionResult 携带 source message IDs 和 summary，由应用服务在一个事务中替换。
- Repository 只 add/execute/flush，应用服务拥有 commit/rollback。
- ToolResult 和 TurnOutcome 使用结构化状态；CLI/GUI 只消费终态，不从“generator 是否抛异常”推断成功。
- 持久化 Message 通过 role 白名单转换成 provider message，不把 DB metadata 发送给 LLM。
- SQLite 每条连接启用 foreign keys；开发库允许重建，不引入迁移框架。

## 6. Core、Adapter 与包归属

### 6.1 当前依赖泄漏

```text
文档目标
cli / gui -> application/runtime -> core ports
                                 -> services -> db
                                 -> llm/mcp/skills/tools adapters
config     -> typed values only

当前关键泄漏
core   -> tools.NoopToolRegistry / skills.SkillRegistry / OpenAI wire shape
tools  -> db / services / skills，并创建具体运行时对象
skills -> tools.response，形成 tools <-> skills cycle
gui    -> db repositories / ORM
config -> network / HOME cache write
```

### 6.2 建议归属

| 当前符号 | 建议归属 | 原因 |
|----------|----------|------|
| `ToolRegistryFactory` | `runtime/tool_assembly.py` | 创建 DB/service/tool graph 属于 composition root |
| `SkillTool` | `tools/skill_tool.py` | 模型可调用 adapter 属于 tools |
| LLM port 和中立 DTO | `core/ports/llm.py` | Port 由消费者 Core 所有 |
| `ToolSpec` | `core/ports/tools.py` | Core 需要的工具契约不应由 adapter 反向提供 |
| Provider metadata/catalog | `llm/provider_catalog.py` | 属于 provider adapter，不是 typed config |
| `MCPConfig` | `config/mcp.py` | 配置应在启动时完成类型校验 |
| `CliCallback` | `cli/permission_callback.py` | 终端 input/print 属于 presentation |
| `PermissionEngine` | 保留 `permission/`，声明为 core-domain package | 避免无收益的大搬迁 |
| `MemoryProtocol` / `AgentMemory` | 当前删除 | 尚无已批准的 Memory 功能 |

### 6.3 Provider metadata

当前 Config getter 可能同步访问 models.dev 并写 `~/.intelliagent/providers.json`，违反“config only typed settings”，
且会在 async Runtime 路径阻塞事件循环。

整改后的解析顺序为：显式配置覆盖 > 24 小时内的有效缓存 > 最多 3 秒的远程获取。缓存必须包含目标
`provider/model` 和正整数 context limit。配置与缓存均不可用且远程失败时，Runtime 启动失败并输出可操作诊断。

## 7. 文件粒度判断

### 7.1 应保留的拆分

| 区域 | 判断 | 理由 |
|------|------|------|
| `cli/{main,parser,application,presenter}.py` | 保留 | 入口、解析、流程和展示有不同变化原因 |
| `db/repositories/*.py` | 保留 | 按表分文件合理，问题是 commit 所有权而非文件数 |
| `skills/{model,loader,registry}.py` | 保留 | 模型、文件解析和索引是独立 seam |
| `runtime/{database_runtime,engine_factory,mcp_integration}.py` | 保留 | 分别拥有明确资源生命周期 |
| `gui/styles/minimax_qss.py` | 保留 | 样式数据行数大不代表职责过多 |
| `tools/file_tools.py` | 暂保留 | 三个文件操作共享限制和响应契约 |

### 7.2 应移动或收口的区域

| 区域 | 问题 | 动作 |
|------|------|------|
| `tools/registry.py` | Registry、schema、built-ins 和 runtime assembly 混合 | 移走 Factory，不按工具继续膨胀 |
| `gui/main_window.py` | UI、命令、CRUD、历史映射和状态混合 | 抽走应用用例，不继续拆纯 UI 私有方法 |
| `skills/runtime.py` | 名为 Runtime，实际是 config-to-loader bridge | 移入 Runtime assembly 或改名 |
| `skills/tool.py` | 包归属错误并制造循环 | 移入 tools |
| `types/` | 收容 LLM port、provider metadata 和未使用 Memory | 按消费者/adapter 归位后删除通用包 |
| `permission/` | Core policy、CLI adapter、config factory 混合 | 保留 policy，移走 presentation 和装配 |

## 8. 重复与测试问题

- `LLMResponse` 和 `LLMResponseProto` 定义相同字段但没有名义关系。
- PathPolicy 与 path_utils 重复实现已经产生真实行为差异。
- 至少 5 个测试文件重复创建 async SQLite engine/session fixture。
- Agent Team 的 repo/service/tool/registration/integration 测试共 854 行，但生产 Engine 的 FK/WAL 路径仍未被约束。
- 现有 7 个真实 LLM E2E 默认因 API key 跳过，其中 `iter_steps()` 仍使用过期参数。
- `tests/unit/test_main.py` 实际测试 Runtime，没有导入 CLI。
- CI 已运行 Ruff、format 和 pytest，但未把后台线程、unraisable、unawaited coroutine 和资源 warnings 升级为失败。

最低测试门禁应包含：

- PermissionEngine -> ToolExecutor -> MCP wrapper。
- 生产 SQLite FK、事务 rollback、compaction restart。
- 三个并发 turn 的 FIFO 顺序、cancel 清队列、唯一 cancelled outcome。
- Engine error / tool error / permission rejection 的结构化终态。
- Runtime shutdown 后零后台线程和资源 warning。
- 精确 import boundary 测试。
- GUI 创建、恢复、删除、执行 turn、权限确认和历史恢复 smoke。

## 9. 精确依赖规则

- `src/core` 不得 import `src.db`、`src.tools`、`src.skills`、`src.llm`、`src.mcp`、`src.runtime`、`src.gui`、
  `src.cli`、`src.config`、`src.services`。`src.permission` 作为声明过的 core-domain package 可被 Core 使用。
- `src/gui` 不得 import `src.db`、SQLAlchemy ORM 或 Repository。
- `src/config` 不得 import/调用网络客户端，也不得执行用户目录缓存写入。
- `src/tools` 不得 import `src.runtime`、`src.db` 或 SQLAlchemy，不得创建 Service/Runtime graph。
- Tools 中的 schema 指工具参数 JSON Schema；Core-owned ToolSpec/DTO 不由 Tools 包定义。

## 10. 验证基线

- `uv run pytest --tb=short`: 416 passed、7 skipped；资源 warnings 数量非零且随线程竞态波动，曾观察到 2、3、4 条。
- `uv run ruff check .`: 通过。
- `uv run ruff format --check .`: 通过。
- MCP 默认权限探针: `allow`。
- SQLite 外键探针: `foreign_keys=0`。
- 第二 external directory 探针: `allowed=False`。

## 11. 不纳入本次修复

- 新 provider、Memory、Web/API、Agent Worker/Bus。
- 删除或替换现有 PyQt5 GUI。
- 深色主题、QFluentWidgets 或 GUI 视觉重做。
- legacy SQLite 无损迁移。
- 远端服务端确认取消或停止计费。
- 完整 Clean Architecture、DDD Mapper 或插件框架。
- 跨进程队列、性能专项和其他新产品能力。
- Release 和包分发。

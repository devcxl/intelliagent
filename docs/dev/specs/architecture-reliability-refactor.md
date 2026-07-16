# 技术方案：IntelliAgent 架构可靠性修复

- **状态**: Proposed
- **日期**: 2026-07-16
- **Parent Issue**: [#46](https://github.com/devcxl/intelliagent/issues/46)
- **PRD**: `docs/prd/architecture-reliability-refactor.md`
- **审查基线**: `main@79509b3`

## 1. 设计目标

本方案在不引入完整 Clean Architecture、插件框架或第二个 LLM provider 的前提下，解决四个所有权问题：

1. Core 拥有 provider-neutral LLM/Tool 契约和工具安全策略。
2. Runtime 是唯一 composition root 和资源生命周期所有者。
3. ConversationApplication 是唯一 active Conversation 所有者。
4. Service 拥有事务，Repository 只负责数据访问。

修复分为 P0 / P1 / P2，小批次实施；任何实施 PR 最多修改 10 个文件。

## 2. 已批准的关键决策

| 决策 | 选择 |
|------|------|
| Conversation 应用入口 | 新增 `ConversationApplication`，AgentRuntime 只管理资源生命周期 |
| 工具授权位置 | `ToolExecutor` 留在 Core，Runtime 注入 Registry/Permission/Callback |
| 工作区路径边界 | 已声明本地路径的越界检查是硬边界，用户规则不可覆盖 |
| 默认 MCP 权限 | `ask`，用户可覆盖默认规则，但不能突破本地路径硬边界 |
| Turn 并发 | 单 Conversation FIFO |
| Turn 终态 | 统一 `terminal` 事件，状态为 success/error/cancelled |
| 取消 | 清 active/queued turn；本地强保证；远端终止 best-effort |
| 数据兼容 | 开发库允许重建，不引入 migration 框架 |
| Provider metadata | 显式配置 > 24h 缓存 > 3 秒远程获取；失败则启动失败 |
| HTTP client | 直接依赖 `httpx`，使用异步 client 和总 deadline |
| Planning PR | 需求 3 文件 + 本方案 + 3 ADR，共 7 文件 |

## 3. 非目标

- 不新增 LLM provider、Memory、Web/API、Agent Worker/Bus 或插件框架。
- 不删除或替换 PyQt5 GUI，不实现深色主题或 QFluentWidgets。
- 不保证已完成的文件、shell、MCP 等外部副作用回滚。
- 不保证远端 LLM/MCP 服务确认取消或停止计费。
- 不引入通用 UnitOfWork、Repository Protocol、Domain Mapper 或事件总线。

## 4. 目标架构

```text
CLI / GUI
    -> ConversationApplication
        -> ConversationSession (FIFO + cancel state)
        -> ConversationService / TaskService / AgentTeamService
            -> Repository
                -> SQLAlchemy AsyncSession

AgentRuntime
    -> ProviderCatalog / OpenAICompatibleClient
    -> PermissionEngine / PathPolicy
    -> ToolRegistry / MCP / Skills
    -> ConversationApplication
    -> DatabaseRuntime

ReactEngine
    -> LLMClientPort
    -> ToolExecutor
        -> PermissionEngine
        -> ToolRegistryPort
```

### 4.1 目标包布局

```text
src/
├── core/
│   ├── ports/
│   │   ├── llm.py
│   │   └── tools.py
│   ├── context_manager.py
│   ├── events.py
│   ├── react_engine.py
│   └── tool_executor.py
├── permission/
│   ├── engine.py
│   ├── path_policy.py
│   └── types.py
├── runtime/
│   ├── agent_runtime.py
│   ├── assembly.py
│   ├── conversation_application.py
│   ├── conversation_session.py
│   ├── database_runtime.py
│   ├── engine_factory.py
│   ├── mcp_integration.py
│   └── tool_assembly.py
├── services/
│   ├── agent_team.py
│   ├── conversation_service.py
│   └── task_service.py
├── tools/
│   ├── registry.py
│   ├── skill_tool.py
│   └── *_tools.py
├── skills/
│   ├── loader.py
│   ├── model.py
│   └── registry.py
├── llm/
│   ├── openai_compatible.py
│   └── provider_catalog.py
├── config/
│   ├── mcp.py
│   ├── provider_config.py
│   └── unified_config.py
└── cli/
    └── permission_callback.py
```

最终删除：

- `src/types/`
- `src/config/provider_registry.py`
- `src/skills/tool.py`
- `src/skills/runtime.py`
- 未使用的 `MemoryProtocol` 和 `AgentMemory`

## 5. Core 契约

### 5.1 Tool 契约

```python
# src/core/ports/tools.py
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    source: str
    local_path_fields: tuple[str, ...] = ()


class ToolStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    REJECTED = "rejected"
    NO_CALLBACK = "no-callback"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ToolResult:
    status: ToolStatus
    content: str = ""
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    conversation_id: str
    turn_id: str
    turn_sequence: int
    cancellation_generation: int
    cancellation: "CancellationToken"


class CancellationToken(Protocol):
    def raise_if_cancelled(self) -> None: ...


class ToolHandler(Protocol):
    async def __call__(
        self,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult: ...


class ToolRegistryPort(Protocol):
    def specs(self) -> tuple[ToolSpec, ...]: ...
    def get_spec(self, name: str) -> ToolSpec | None: ...
    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult: ...
```

约束：

- `input_schema` 保存完整 JSON Schema 根对象。
- `local_path_fields` 只声明 Runtime 能直接验证的本地路径参数；MCP server 内部资源不属于本地沙箱保证。
- Registry owner 是注册参数，不进入 Core-owned ToolSpec。
- Tool adapter 返回 ToolResult，不再返回表示错误的普通 JSON 字符串。

### 5.2 LLM 契约

```python
# src/core/ports/llm.py
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol, Sequence, TypedDict


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: Any
    arguments_error: str | None = None


class CanonicalMessage(TypedDict, total=False):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: tuple[ToolCall, ...]
    tool_call_id: str


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True, slots=True)
class LLMResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)


class LLMClientPort(Protocol):
    async def complete(
        self,
        messages: Sequence[CanonicalMessage],
        *,
        tools: Sequence[ToolSpec] = (),
        temperature: float = 0.3,
    ) -> LLMResponse: ...

    async def aclose(self) -> None: ...
```

Core 不再访问 `tc.function.name`、`usage.prompt_tokens` 或 `get_openai_tools()`。CanonicalMessage 是 Core-owned、
SDK-neutral 的最小消息结构；OpenAI-compatible adapter 是唯一负责 SDK DTO、wire message 和 function schema 转换的位置。

Adapter 必须保留 arguments parse failure，不能把非法 JSON 静默转换为 `{}`。ToolExecutor 只在 arguments 是 object 且
`arguments_error is None` 时继续；本次不引入通用 JSON Schema validator，业务字段校验仍由 Tool adapter 完成。

CanonicalMessage 转换必须拒绝不符合 role 白名单的形状；assistant 的 tool_calls 若存在则必须非空，tool 消息必须包含非空
tool_call_id。

### 5.3 Engine 与 Turn 终态

Core 使用 `EngineResult` 表达 ReAct loop 结果；Runtime 使用 `TurnOutcome` 增加 conversation/turn 上下文。

```python
@dataclass(frozen=True, slots=True)
class EngineResult:
    status: Literal["success", "error", "cancelled"]
    answer: str = ""
    error_code: str | None = None
    error_message: str | None = None
    steps: int = 0
    usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass(frozen=True, slots=True)
class TurnOutcome:
    context: ToolExecutionContext
    result: EngineResult
```

ReactEngine 不再以 async generator 同时承担事件流和结果返回，改为显式 event sink：

```python
EventSink = Callable[[dict[str, Any]], Awaitable[None]]


async def execute(
    self,
    task: str,
    context: ToolExecutionContext,
    emit: EventSink,
) -> EngineResult: ...
```

ReactEngine 只 emit thought/action/observation 并返回 EngineResult。ConversationSession 在 persistence plan 成功提交后构造
唯一 terminal；所有终态通过幂等 `_finish_turn_locked()` 完成。TurnHandle.events() 包含同一个 terminal，wait() 返回同一个
TurnOutcome。

ReactEngine 在每次 awaited LLM complete 返回后、emit action 前检查 `context.cancellation`；已取消时不调用 ToolExecutor 并返回
cancelled EngineResult。ToolExecutor 在 Permission Callback 返回后、Registry.invoke 前再次检查，覆盖“已展示 action 但 handler
尚未启动”的取消窗口。

TurnHandle 为单消费者事件流维护 Session-owned queue，并单独维护 terminal Future；event sink 写队列不依赖消费者继续迭代。
取消 events() 消费或提前退出不会取消 runner，wait() 仍返回唯一 TurnOutcome。事件数受 Engine max steps 限制。

事件仍使用可序列化 dict，避免引入事件类层次，但必须由集中构造函数生成：

```text
thought -> action -> observation -> ... -> terminal
```

- action 在调用工具前发出。
- observation 完整保留 ToolResult status/error。
- 每个已接收 turn 恰好一个 terminal。
- terminal 只有 success/error/cancelled 三种状态。
- 移除 EventBridge 对 generator 结束即成功的推断。

## 6. fail-closed 与 PathPolicy

### 6.1 ToolExecutor 顺序

```text
校验 ToolCall
  -> 获取 ToolSpec
  -> 检查 arguments parse error / object 类型
  -> PathPolicy 硬边界
  -> PermissionEngine 用户规则/默认规则
  -> 必要时调用 Callback
  -> CancellationToken 二次检查
  -> Registry.invoke
  -> 返回 ToolResult
```

### 6.2 决策矩阵

| 场景 | status | error_code | Callback | Handler |
|------|--------|------------|----------|---------|
| arguments 非 object | error | INVALID_PARAMETERS | 0 | 0 |
| 工具不存在 | error | UNKNOWN_TOOL | 0 | 0 |
| Registry.get_spec 异常 | error | REGISTRY_ERROR | 0 | 0 |
| PermissionEngine 缺失 | denied | PERMISSION_ENGINE_MISSING | 0 | 0 |
| PermissionEngine 异常 | denied | PERMISSION_CHECK_ERROR | 0 | 0 |
| PathPolicy 异常 | denied | PATH_POLICY_ERROR | 0 | 0 |
| 本地路径越界 | denied | PATH_OUTSIDE_WORKSPACE | 0 | 0 |
| deny | denied | PERMISSION_DENIED | 0 | 0 |
| ask 且无 Callback | no-callback | PERMISSION_CALLBACK_MISSING | 0 | 0 |
| ask 且拒绝/超时 | rejected | PERMISSION_REJECTED | 1 | 0 |
| Callback 异常 | error | PERMISSION_CALLBACK_ERROR | 1 | 0 |
| allow | handler 原结果 | - | 0 | 1 |
| ask 且批准 | handler 原结果 | - | 1 | 1 |
| handler 异常 | error | EXECUTION_ERROR | - | 1 |
| 执行取消 | cancelled | TOOL_CANCELLED | - | <=1 |

### 6.3 规则优先级

```text
1. ToolSpec.local_path_fields 对应的 PathPolicy 硬边界
2. 用户规则 last-match-wins
3. external directory 默认 ask
4. 默认规则 last-match-wins
5. ask 兜底
```

默认规则删除 `("mcp *", "allow")`。用户可以覆盖默认 `.env*` 和 MCP 规则，但不能放行已声明本地路径的工作区越界。
未声明资源语义的 MCP 工具默认 ask；Runtime 不声称能沙箱化 MCP server 内部访问。

Runtime 创建一个 PathPolicy 实例，同时注入 PermissionEngine 和文件工具。`PathPolicy.check()` 对每个 external directory
独立捕获 `relative_to()` 失败，不能在第一个不匹配目录退出。

`local_path_fields` 仅支持顶层、非空字符串字段；每个已提供字段都必须通过。Executor 在 copied arguments 中把字段替换为
PathPolicy 返回的规范化绝对路径，再调用 handler。读路径和已存在目标使用 `resolve()`；新写入目标先规范化现有父目录再拼接
最终文件名。空值、数组、嵌套值或解析异常均 fail closed。

该边界防止 Agent 通过正常工具参数越界，不承诺抵御另一个本地恶意进程在检查后并发替换 symlink 的 TOCTOU 攻击；文件工具
仍在实际 I/O 前复用同一 PathPolicy 做第二次检查。

本次只在 Executor 中验证 arguments parse/object 和本地路径，不引入 `jsonschema` 运行时依赖。完整 schema 用于模型约束；
Tool adapter 在产生副作用前完成自身字段/业务校验并返回 INVALID_PARAMETERS。

## 7. ToolRegistry 与 MCP

### 7.1 注册所有权

```python
class RegistrationToken:
    """Registry 创建的 opaque lease；调用方不能自行构造。"""
    ...


class ToolRegistry(ToolRegistryPort):
    def register(
        self,
        spec: ToolSpec,
        handler: ToolHandler,
        *,
        owner: str,
    ) -> RegistrationToken: ...
    def unregister(self, token: RegistrationToken) -> bool: ...
```

规则：

- 同名注册抛 `DuplicateToolError`，不提供静默 replace。
- 删除按 name 注销的公开 API。
- stale token 或其他 owner 的 token 不能删除当前注册项。
- Registry 在 register 写入和 specs/get_spec 读出时都对嵌套 input schema 执行 `deepcopy()`。

owner 命名：

```text
runtime:builtin
runtime:skills
runtime:tasks
runtime:agent-team
mcp:<server-name>:<connection-id>
```

### 7.2 MCP schema

删除 `_tool_params_to_openai()`。MCP 注册时原样保存 `inputSchema`，包括 nested properties、items、enum、oneOf、anyOf、
`$defs` 和 `additionalProperties`。OpenAI adapter 在请求前把 ToolSpec 转换为 provider schema。

每条 MCP connection 保存自己的 RegistrationToken 列表。部分注册失败时，只回滚本 connection 已注册 token；stop 时按 token
注销，不按工具名删除。

MCP adapter 显式映射执行结果：`CallToolResult.isError=True` 返回 `ToolStatus.ERROR/MCP_TOOL_ERROR`；文本 content blocks
按顺序拼接，`structuredContent` 以 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 追加在
`[structured]` 标记后。非文本 block 只追加 `{"type":"<type>","omitted":true}`，本次不引入 artifact 存储。

最终 content 按 UTF-8 计最多 32 KiB；超限时在上限内保留前缀并追加 `...[truncated: original_bytes=N]`。文本、structured、
非文本和 error 结果均使用同一确定性映射并有回归测试。

## 8. ConversationApplication

### 8.1 唯一所有权

```text
ConversationApplication
    _active_session: ConversationSession | None  # 唯一权威 active 状态

ConversationSession
    conversation_id: str                         # 构造后不可变
    _queue: deque[TurnRequest]
    _active: RunningTurn | None
    _state: idle/running/cancelling/closed
```

删除：

- `ConversationService._conversation_id/_is_new/_warnings`
- `AgentRuntime._session`
- `AgentRuntime.switch_session()` 的私有字段写入
- `EventBridge._pending_session_id`
- GUI 对 active Conversation 的权威镜像

GUI 可以保存列表选中项用于显示，但工具和持久化只能使用 TurnContext。

### 8.2 公开 API

```python
class ConversationApplication:
    @property
    def active_conversation_id(self) -> str | None: ...

    async def create(self, title: str = "") -> ConversationDetail: ...
    async def open(self, conversation_id: str) -> ConversationDetail: ...
    async def delete(self, conversation_id: str) -> None: ...
    async def list(self, limit: int = 100, offset: int = 0) -> tuple[ConversationSummary, ...]: ...
    async def load(self, conversation_id: str) -> ConversationDetail: ...
    async def submit_turn(self, text: str) -> TurnHandle: ...
    async def cancel_active(self) -> tuple[TurnOutcome, ...]: ...
    async def close(self) -> None: ...


class TurnHandle:
    context: ToolExecutionContext
    def events(self) -> AsyncIterator[dict[str, Any]]: ...
    async def wait(self) -> TurnOutcome: ...
```

`AgentRuntime.conversations` 暴露该入口。CLI/GUI 不再调用 Runtime 的会话代理方法或获取 session factory。

`active_conversation_id` 是单事件循环内的只读快照；所有状态修改仍通过持 `_owner_lock` 的 async 命令完成。该属性不提供跨线程
同步保证，GUI 不得据此绕过命令级 busy 校验。

### 8.3 命令语义

| 方法 | 语义 |
|------|------|
| create | busy 指存在 active/queued turn；busy 时拒绝，idle 时关闭旧 session 后创建并原子替换 active |
| open | 目标必须存在；busy 时拒绝，idle 时关闭旧 session 后原子替换，不隐式创建 |
| delete | busy 时拒绝；删除 active-idle Conversation 成功后关闭旧 session 并令 active=None |
| delete（目标非 active） | 直接删除目标 DB 记录，不关闭或替换当前 active-idle session |
| load | 只读，不改变 active owner |
| submit_turn | 无 active 时返回 `NO_ACTIVE_CONVERSATION`；队列锁内分配 turn_sequence 并返回 handle |
| cancel_active | 取消 active 和 queued；重复调用等待同一取消过程 |
| close | 拒绝新 turn，取消并等待本地清理 |

create/open/delete 的 DB 操作失败时保留原 active session；应用 CLOSED 后所有命令返回 `APPLICATION_CLOSED`。

## 9. FIFO 与取消状态机

```text
IDLE
  submit -> RUNNING
  close  -> CLOSED

RUNNING
  submit -> RUNNING + queued
  success/error + queue -> RUNNING(next)
  success/error + empty -> IDLE
  cancel/close -> CANCELLING

CANCELLING
  submit -> RUN_CANCELLING
  create/open/delete -> CONVERSATION_BUSY
  cleanup -> IDLE 或 CLOSED
```

### 9.1 线性化点

所有 enqueue、cancel 和 terminal finalization 使用同一个 `ConversationSession._queue_lock`：

- enqueue：持锁分配递增 turn_sequence 并 append。
- cancel：持锁设置 CANCELLING、detach active、清空 queued、递增 cancellation generation，并创建/复用 `_cancel_task`。
- success/error：持锁校验 generation，提交短事务后完成 terminal。
- success 与 cancel 只能有一个先获得锁；先获得者决定唯一终态。

锁顺序固定为：

```text
ConversationApplication._owner_lock -> ConversationSession._queue_lock
```

worker 禁止反向获取 owner lock。锁内禁止等待 runner、Future、GUI callback、LLM、工具或 cancel cleanup；success 持锁执行的
唯一 await 是有时限的短 DB transaction。禁止持 DB transaction 后再获取 owner/queue lock。

### 9.2 取消步骤

1. 持队列锁进入 CANCELLING，detach active、清空 queued、完成 queued cancelled terminal；不等待 active runner。
2. 释放队列锁，在 Session-owned `_cancel_task` 中取消 active runner、LLM request/stream 和 tool task。
3. shell 执行 `terminate -> wait(2s) -> kill -> wait(2s)`；第二次超时记录 cleanup error 并继续 Runtime 关闭；MCP 只取消当前
   request await，不关闭共享 session。
4. generation guard 停止继续消费 Engine，并丢弃 late event 和 DB persistence plan。
5. active user message可以保留；assistant/tool 业务消息不提交。
6. 使当前 Engine 失效，下次 turn 从 DB 重建。
7. cleanup 完成后重新获取队列锁，通过幂等 `_finish_turn_locked()` 完成 active cancelled terminal，并进入 IDLE。

重复 cancel 使用 `asyncio.shield()` 等待同一个 `_cancel_task`，不会重复取消或产生第二个 terminal。调用 cancel 的上层 task 自身被
取消时，Session-owned cleanup 仍继续执行。

已完成的文件、shell、MCP 和其他外部副作用不回滚。

## 10. 事务与持久化

### 10.1 Repository 契约

目标状态下 Repository 只允许 add/delete/execute/flush，不允许 commit、rollback、创建或关闭 session。

```python
async def save(self, obj: ModelT) -> ModelT:
    self._session.add(obj)
    await self._session.flush()
    return obj
```

Service 使用：

```python
async with session_factory.begin() as session:
    ...
```

事务不得跨越 LLM、工具、权限弹窗或 Qt 交互。

### 10.2 Service 边界

| 用例 | 事务 |
|------|------|
| create/delete Conversation | 每个应用命令一个短事务 |
| active turn user message | turn 开始时独立短事务 |
| turn success | assistant/tool batch + compaction + updated_at 一个事务 |
| compaction | delete source + insert summary 一个事务 |
| Task add_many | 验证全部输入后一个事务 |
| Agent Team mutation | 每个 Service 方法一个事务 |
| list/load | 独立短 session，只读 |

TaskService 从 P2 前移到 P1，保证批量 Task 原子性；P2 只做 Tools 包依赖门禁。

TaskService 的 get/update/finish 接口必须接收 conversation_id，并以 `task_id + conversation_id` 查询；parent task 也必须属于同一
Conversation。找不到或跨 Conversation 一律返回同一个 TASK_NOT_FOUND，不泄漏其他 Conversation 是否存在该 task。

迁移必须按 Conversation、Task、Agent Team 三个垂直切片进行，禁止先全局删除 `BaseRepository.save()` 的 commit：

1. 为目标 Repository 增加 flush-only API，旧 commit API 暂时只服务未迁移调用方。
2. 同一 PR 内让对应 Service 接管 session/transaction，并迁移 Tool/Runtime 调用方。
3. 每个领域迁移后验证持久化和 rollback。
4. 所有调用方迁移完成后，最后删除共享 commit API，并启用 Repository 契约测试。

### 10.3 Message 顺序

Message 新增：

```text
message_sequence INTEGER NOT NULL
UNIQUE(conversation_id, message_sequence)
is_summary BOOLEAN NOT NULL DEFAULT FALSE
compression_count INTEGER NULL
```

turn_sequence 只表示当前 ConversationSession 内的 FIFO 顺序，session 重建后可从 1 开始；message_sequence 是数据库内每条
Message 的持久顺序，两者不得混用。

ConversationService 是 Message 单写者：激活 session 时读取 `MAX(message_sequence)`，在内存分配后续 message_sequence；
user 和 plan message 产生时预留独立序号，取消允许出现空洞。UNIQUE 约束已提供索引，不再增加相同普通索引。

按 message_sequence 加载，不依赖可能相同的 created_at。项目允许重建开发库，不提供 migration。

### 10.4 Provider message 白名单

| DB role | 允许字段 |
|---------|----------|
| user | role, content |
| assistant | role, content, 可选规范化 tool_calls |
| tool | role, content, tool_call_id |

禁止发送 id、conversation_id、message_sequence、created_at、tool_name、tool_args、ORM state 和未知 metadata。
assistant 的 tool_calls 若存在必须非空；tool 的 tool_call_id 必须非空，否则返回 MESSAGE_FORMAT_INVALID。

P1-E mapper 返回当前 OpenAI-compatible client 已接受的全新 plain dict，只负责 role 白名单和顺序，不引入临时 DTO。P2-A 再把
mapper 输出和 LLM port 一次性切换为 CanonicalMessage/OpenAI wire mapping；持久化字段和 P1 验收语义不变。

### 10.5 Turn persistence plan

- queued turn 不写 Message。
- active turn 开始时提交 user message，并返回真实 message ID/message_sequence，以同一身份加入 ContextManager。
- 每条待提交 assistant/tool message 拥有唯一 `plan_message_id = f"{turn_id}:{ordinal}"`（ordinal 从 1 递增）和预分配
  message_sequence。
- assistant/tool messages 和 compaction 先保存在内存 TurnPersistencePlan。
- success terminal 前在一个事务中提交 plan。
- error/cancelled 丢弃 plan；不保存 assistant/tool 业务消息。
- terminal success 只有在 DB commit 完成后发出；commit 失败返回 error terminal。
- 任何 error/cancelled/commit failure 都使 Engine 失效；下一 turn 从 DB 重建，避免未持久化上下文污染后续请求。

## 11. Context compaction

保留 ADR 0001 的确定性 summary、75% 阈值、稳定 instruction prefix 和 user-role summary。

扩展 ContextSummary：

```python
@dataclass(frozen=True)
class ContextSummary:
    content: str
    source_message_count: int
    compression_count: int
    source_message_ids: tuple[str, ...]
    consumed_plan_message_ids: tuple[str, ...]
```

ContextManager 区分两种身份：已持久化消息的 message ID，以及当前 turn 待提交消息的 plan_message_id。每次 compaction 同时记录
被摘要吸收的两组 ID；连续 compaction 合并前一 summary 的两组 ID 和 compression_count。

success 事务只插入最后一次 compaction 后新增、未被 consumed_plan_message_ids 吸收的 plan messages：

```text
BEGIN
  验证 source IDs 全部属于当前 conversation
  验证实际数量等于去重后的 source IDs 数量
  DELETE source messages
  INSERT summary(role=user, is_summary=true,
                 compression_count=N,
                 message_sequence=全部 consumed 消息的最小 sequence)
  INSERT 未被最终 summary 消费的 plan messages
  UPDATE conversation.updated_at
COMMIT
```

冲突返回 `COMPACTION_CONFLICT` 且不做部分替换。成功提交包含 compaction 时也使 Engine 失效，下一 turn 从带新 summary ID 的 DB
重载；error/cancel/DB failure 同样使 Engine 失效。重启通过 `is_summary/compression_count` 识别 summary，不依赖内容前缀。

## 12. SQLite 与资源生命周期

### 12.1 Foreign keys

按照 SQLAlchemy 2 SQLite dialect 建议，在 async engine 的 `sync_engine` connect event 上对每条 DBAPI connection 执行
`PRAGMA foreign_keys=ON`。监听器必须在连接进入 pool 前运行；测试通过生产 `create_engine()` 验证每个新连接为 1。

### 12.2 AgentRuntime 状态

```text
NEW -> STARTING -> RUNNING -> STOPPING -> CLOSED
```

- 构造函数只保存 config/factories，不执行网络或创建资源。
- initialize 先由 Runtime 解析显式 context limit；缺失时在 bootstrap-scoped HTTPX client 中调用 ProviderCatalog，随后初始化 DB、
  创建 LLM/Tools/Permission、启动 MCP、创建 ConversationApplication。
- 初始化中途失败时反向关闭已获得资源。
- shutdown 幂等；即使某个 closer 失败也继续关闭其余资源，最后汇总错误。
- 关闭顺序：ConversationApplication -> MCP -> LLM client -> DatabaseRuntime。
- CLI 所有入口使用 try/finally 或 `async with AgentRuntime(...)`。
- GUI 必须 await shutdown 完成后再退出 qasync loop。

### 12.3 Async clients

- P0-H 先把现有 LLM adapter 改为 `AsyncOpenAI`，移除 `asyncio.to_thread()`，并为具体 client 增加可 await 的 close；这是 P1
  request/stream 取消强保证的前置条件。
- P2-A 再引入 LLMClientPort `aclose()` 和 provider-neutral DTO；OpenAI adapter 实现为 `await AsyncOpenAI.close()`，不重复迁移
  transport。
- ProviderCatalog 借用 bootstrap 创建的 `httpx.AsyncClient`，不拥有也不关闭 client；context limit 解析完成后 bootstrap 立即关闭。
- turn cancel 只取消当前 request/stream，不关闭共享 client。

## 13. ProviderCatalog

### 13.1 接口

```python
class ProviderCatalog:
    def __init__(
        self,
        *,
        cache_file: Path,
        client: httpx.AsyncClient,
        ttl_seconds: float = 86_400,
        total_deadline_seconds: float = 3.0,
        now: Callable[[], float] = time.time,
    ) -> None: ...

    async def get_context_limit(self, provider_id: str, effective_model_id: str) -> int: ...
```

Runtime 默认传入 `Path.home() / ".intelliagent" / "providers.json"`；测试可注入临时路径。新 versioned schema 无法解析旧 raw
models.dev cache 时按 cache miss 处理，不尝试原地兼容旧内容。

### 13.2 解析顺序

```text
显式 provider.<id>.models.<model_key>.limit.context
  -> 24 小时内有效缓存
  -> models.dev 远程获取
  -> 启动失败
```

该优先级由 Runtime resolver 实现，而不是 ProviderCatalog 自己读取 Config：

```python
async def resolve_context_limit(config: UnifiedConfig) -> int:
    model_ref = resolve_model_reference(config, config.model)
    explicit = resolve_explicit_limit(config, model_ref.provider_id, model_ref.model_key)
    if explicit is not None:
        return validate_positive_limit(explicit)
    async with httpx.AsyncClient() as client:
        catalog = ProviderCatalog(cache_file=..., client=client)
        return await catalog.get_context_limit(model_ref.provider_id, model_ref.effective_model_id)
```

缓存：

```json
{
  "version": 1,
  "models": {
    "openai/gpt-4o-mini": {"context_limit": 128000}
  }
}
```

- key 为 `provider_id/effective_model_id`。
- 远程值只从 `response[provider_id].models[effective_model_id].limit.context` 读取，再规范化为上述 versioned cache schema。
- 显式配置、缓存和远程三种来源的 context_limit 都必须是非 bool 的正整数。
- cache mtime 满足 `0 <= age <= 86400`。
- 过期、损坏、缺 key 或非法值均视为 miss。
- 外层 `asyncio.timeout(3.0)` 覆盖 DNS、连接和读取；不重试。
- 成功后同目录临时文件 + `os.replace()` 原子写入。
- 已取得可信 limit 后缓存写失败只记录 warning，不阻止启动。
- 配置/缓存均不可用且远程失败时，Runtime 以明确错误启动失败。

模型引用由 Runtime 按以下兼容矩阵解析；disabled 优先于 enabled：

| 配置 | 结果 |
|------|------|
| model 为空 | `MODEL_REFERENCE_INVALID` |
| `provider_id/model_id` 且 provider enabled | 使用该 provider |
| 带前缀但 provider 不存在或 disabled | `MODEL_PROVIDER_UNAVAILABLE` |
| 无前缀且恰有一个 enabled provider | 使用唯一 provider，model 字符串作为 model key |
| 无前缀且没有 enabled provider | `MODEL_PROVIDER_UNAVAILABLE` |
| 无前缀且有多个 enabled provider | `MODEL_REFERENCE_AMBIGUOUS` |

enabled provider 集合先取 `config.provider` keys；`enabled_providers` 非 None 时取交集，再移除 `disabled_providers`。OpenAI adapter
最终发送 effective model ID，不得把完整 `provider_id/model_id` 传给 SDK：

```text
model_key = 引用中去掉 provider 前缀后的值
override = provider.models[model_key]（若存在）
effective_model_id = override.id（非 None 时必须是非空字符串）否则 model_key
```

显式 context limit 按 `provider.models[model_key].limit.context` 查询；ProviderCatalog cache/remote key 和 SDK model 参数统一使用
effective_model_id。非空 small_model 使用同一引用解析器；只有当前实际使用的 primary model 触发 context-limit 获取。

Config 包只读取配置文件、执行环境插值和 Pydantic 校验；禁止网络请求、Path.home 缓存和 import `src.llm`。

## 14. GUI 与 CLI

### 14.1 GUI

```text
MainWindow / SessionList -> ConversationApplication -> Service -> short AsyncSession
```

- SessionList 变为纯展示组件，接收 ConversationSummary 并发出 intent。
- MainWindow 使用 ConversationDetail/MessageView 渲染，不持有 ORM/Repository。
- EventBridge 调用 submit_turn/cancel_active，消费 TurnHandle。
- engine_finished 只由 terminal event 映射。
- GUI 启动不再创建长生命周期 AsyncSession。
- 顶层 GUI main coroutine 必须被 qasync loop 真正 await。首次 closeEvent 只发 shutdown intent 并阻止退出；await
  `runtime.shutdown()` 后才允许窗口关闭和 `app.quit()`。
- PermissionDialog 改用 `open()` + Future/finished signal，不在 coroutine 内调用同步 `exec()`；turn cancel 时关闭对话框并完成
  Future，避免 shutdown 等待不可取消的模态调用。
- 保留 PyQt5、qasync、mistune 和现有核心用户流程。

### 14.2 CLI

- CliCallback 移入 `src/cli/permission_callback.py`。
- CLI 使用 ConversationApplication，不直接了解 Session/Repository。
- history/list/load 使用应用 DTO。
- 所有正常、EOF、异常路径都 await Runtime shutdown。

### 14.3 兼容性边界

项目处于 0.1 阶段，不承诺内部 Python import/API 稳定性；不增加长期兼容 wrapper。每个节点必须在同一 PR 迁移全部仓内调用方、
测试和公开导出。

| 当前内部 API | 目标 API | 迁移策略 |
|--------------|----------|----------|
| AgentRuntime.execute/setup_conversation/switch_session/list_conversations/session_factory | AgentRuntime.conversations | P1-K 仓内调用方原子切换后删除旧门面 |
| ReactEngine async generator | ReactEngine.execute(event sink) + TurnHandle | P1-G 保持事件 dict 形状，P1-K 切换消费者 |
| ToolRegistry.call_tool | ToolRegistryPort.invoke | P0-A 引入，P0-B 切换 ToolExecutor 后删除旧调用入口 |
| ToolRegistry.get_openai_tools | ToolRegistryPort.specs | P0-A 引入，P2-A 切换 OpenAI adapter 后删除旧导出入口 |
| ToolRegistry 按名称 unregister | RegistrationToken unregister | P2-C 迁移动态注册调用方后删除旧注销入口 |
| src.types exports | src.core.ports/src.config/src.llm | P2-K 最后删除收容包 |

兼容面仅包括 CLI/GUI 核心流程和现有 intelliagent.json 外部结构。MCP stdio/HTTP 字段保持原样；P2-M 同步 README、
intelliagent.json.example，并新增或修复其引用的 `schemas/intelliagent.schema.json`。

## 15. 依赖门禁

使用标准库 AST 检查 Import 和 ImportFrom，包括 TYPE_CHECKING。

| 包 | 禁止 import 前缀 |
|----|-----------------|
| `src.core` | `src.db`, `src.tools`, `src.skills`, `src.llm`, `src.mcp`, `src.runtime`, `src.gui`, `src.cli`, `src.config`, `src.services`, `sqlalchemy`, `openai`, `mcp` |
| `src.gui` | `src.db`, `sqlalchemy` |
| `src.config` | `src.llm`, `src.runtime`, `src.db`, `src.tools`, `urllib`, `httpx`, `requests`, `aiohttp` |
| `src.tools` | `src.runtime`, `src.db`, `sqlalchemy` |
| `src.skills` | `src.tools`, `src.runtime`, `src.config`, `src.db`, `sqlalchemy` |
| `src.llm` | `src.config`, `src.runtime`, `src.db`, `src.tools`, `src.skills`, `src.mcp`, `src.gui`, `src.cli`, `src.services` |
| `src.permission` | `src.config`, `src.runtime`, `src.tools`, `src.cli`, `src.gui`, `src.db` |
| `src.services` | `src.runtime`, `src.gui`, `src.cli` |
| `src.db` | `src.services`, `src.runtime`, `src.tools`, `src.gui`, `src.cli`, `src.llm`, `src.mcp` |
| `src.mcp` | `src.runtime`, `src.gui`, `src.cli`, `src.services`, `src.db` |
| `src.cli` | `src.db`, `sqlalchemy`, `src.services`, `src.tools` |

合法主方向：

```text
core -> permission
llm -> core
skills -> standard library / Pydantic
tools -> core + permission + skills + services
mcp -> core + tools + config
services -> db
runtime -> concrete packages
cli/gui -> runtime/application
```

AST 测试必须规范化绝对/相对 import、`from src import db` 等形式，并用 `module == prefix or module.startswith(prefix + ".")`
匹配。除禁止矩阵外，构建顶层 package graph 并断言无 strongly connected component。

“Config 不联网”和“Tools 不装配”除 import 测试外，再用行为测试断言网络/构造调用次数为 0。

## 16. 错误码

| 错误码 | 场景 |
|--------|------|
| PERMISSION_ENGINE_MISSING | 无 PermissionEngine |
| PERMISSION_CHECK_ERROR | 权限检查异常 |
| PERMISSION_DENIED | deny |
| PERMISSION_CALLBACK_MISSING | ask 但无 Callback |
| PERMISSION_REJECTED | 用户拒绝或超时 |
| PERMISSION_CALLBACK_ERROR | Callback 异常 |
| PATH_POLICY_ERROR | 路径检查异常 |
| PATH_OUTSIDE_WORKSPACE | 已声明本地路径越界 |
| UNKNOWN_TOOL | 工具不存在 |
| REGISTRY_ERROR | Registry 查询异常 |
| INVALID_PARAMETERS | arguments parse 失败、非 object 或 adapter 业务校验失败 |
| EXECUTION_ERROR | 工具异常 |
| TOOL_CANCELLED | 当前工具执行取消 |
| CONVERSATION_NOT_FOUND | 会话不存在 |
| CONVERSATION_BUSY | active/queued/cancelling 时 create/open/delete |
| RUN_CANCELLING | CANCELLING 时提交 |
| TURN_CANCELLED | turn 被取消 |
| TURN_EXECUTION_ERROR | Engine 执行失败 |
| TURN_PERSISTENCE_ERROR | terminal 提交失败 |
| COMPACTION_CONFLICT | source IDs 与数据库不一致 |
| MESSAGE_FORMAT_INVALID | DB message 无法转换为 provider message |
| TASK_NOT_FOUND | Task 不存在或不属于当前 Conversation |
| MODEL_REFERENCE_AMBIGUOUS | 多 provider 且 model 引用无 provider 前缀 |
| MODEL_REFERENCE_INVALID | model 为空或 ModelOverride.id 为空字符串 |
| MODEL_PROVIDER_UNAVAILABLE | provider 不存在、未启用或已禁用 |
| APPLICATION_CLOSED | ConversationApplication 已关闭 |

命令接受前的错误通过 ApplicationError 抛出；接受后的错误只通过唯一 TurnOutcome/terminal 返回。

## 17. 测试策略

### 17.1 P0

- 完整 fail-closed 决策矩阵，所有拒绝场景 handler 调用次数为 0。
- MCP 默认 ask、`.env` 默认 deny、用户规则覆盖默认规则、路径硬边界不可覆盖。
- 第一个/中间/最后一个 external directory。
- ToolResult 在 Registry -> Executor -> observation -> CLI/GUI 中不丢状态；统一 terminal 在 P1 完成。
- 生产 SQLite engine 每条连接 FK=1，孤儿 Message/Task 写入失败。
- shell cancel 后无遗留进程。
- AsyncOpenAI request task 可取消，concrete client close 被 Runtime 调用一次。
- Runtime 部分初始化、正常关闭、异常关闭均无资源 warning。

### 17.2 P1

- 使用 asyncio.Event/barrier，不使用 sleep 猜时序。
- 3 turn FIFO 的执行/Event 顺序与 turn_sequence 一致，DB 消息顺序与 message_sequence 一致。
- cancel active + 2 queued，各只有一个 cancelled terminal。
- CANCELLING 时 submit 返回 RUN_CANCELLING。
- cancel 与 success 竞争只产生一个 terminal。
- cancel 发生在 action 与 Registry.invoke 之间时不得启动 handler。
- cancel 调用方自身取消时，Session-owned cleanup 仍完成。
- stubborn fake 的 late result 不产生 Event/DB 写入。
- 同一 turn 连续两次 compaction、success 后下一 turn 再 compaction、restart 后识别 summary/compression_count。
- 工具调用后触发 compaction 再重启时，summary 与原始 plan message 不重复。
- Engine error、cancel 和 persistence error 后下一 turn 都从 DB 重建 Engine。
- busy delete/open/create 返回 CONVERSATION_BUSY。
- active-idle Conversation 可安全删除/替换，DB 失败时保留原 active session。
- Task batch 和 compaction rollback。
- 两个 Conversation 间的 Task update/finish/parent 越权均返回 TASK_NOT_FOUND 且不修改数据。
- compaction 重启只恢复 summary + 未压缩消息。
- provider message 精确字段白名单。
- GUI AST 无 DB/ORM/Repository import。
- GUI 在 PermissionDialog、LLM 和工具执行期间关闭时完成 shutdown handshake。
- GUI CI 安装 dev + gui extras，使用 QT_QPA_PLATFORM=offscreen，关键 GUI 用例不得 skip。
- event consumer 提前停止读取不等于取消，Turn 仍可通过 wait() 得到唯一 terminal。
- fake LLM + 真实 Runtime/SQLite/Permission/Tools 集成测试。

### 17.3 P2

- Core DTO 不引用 OpenAI/MCP SDK 类型。
- MCP JSON Schema 深度相等，覆盖 nested/array/enum/oneOf/anyOf/$defs/additionalProperties。
- MCP text/structured/non-text/error 映射和 32 KiB UTF-8 截断格式确定。
- duplicate register、stale token、跨 owner token 和部分注册回滚。
- Provider cache 24h 边界、非法值、3 秒总 deadline、调用次数 1、原子写入。
- 模型引用矩阵覆盖前缀、零/单/多 provider、enabled/disabled、small_model，以及 alias + ModelOverride.id + 无显式 limit 时
  cache/remote/SDK 使用同一 effective model ID；MCP 外部 JSON fixture 不变。
- AST import-boundary 参数化测试。
- CI 将 PytestUnhandledThreadExceptionWarning、PytestUnraisableExceptionWarning、ResourceWarning 和未等待 coroutine 的 RuntimeWarning 视为失败。

## 18. 分批实施 DAG

### P0

```text
P0-A Core ToolSpec/ToolResult/ToolExecutionContext/ToolRegistryPort 契约
  -> P0-B fail-closed + MCP 默认 ask
       -> P0-C PathPolicy 硬边界
       -> P0-D ToolResult/Event 状态
            -> P0-E CLI/GUI 失败传播（保留现有事件形态）

P0-F SQLite FK
P0-G shell cancel cleanup
P0-H AsyncOpenAI transport + concrete client close
P0-I MCP/DB close
P0-H + P0-I -> P0-J Runtime 初始化回滚/shutdown

P0-C + P0-E + P0-F + P0-G + P0-J
  -> P0-K warning-as-error
```

### P1

```text
P1-A 增加 flush-only API + ConversationService 事务切片
  -> P1-B TaskService/TaskTools 事务切片
  -> P1-C AgentTeamService/Tools 事务切片
       -> P1-D 删除旧 commit API + Repository 契约门禁
             -> P1-E message_sequence + role-whitelist plain-dict mapper
                 -> P1-F ConversationApplication + idle replacement
                      -> P1-G callback-based Engine + TurnPersistencePlan
                           -> P1-H FIFO
P0-H + P1-H              -> P1-I cancel token/state machine
                 P1-G -> P1-J compaction 双身份跟踪 + 原子替换

P1-I + P1-J -> P1-K CLI/GUI 应用入口与 shutdown handshake
             -> P1-L deterministic Runtime 集成门禁
```

### P2

```text
P2-A CanonicalMessage/LLM DTO + OpenAI wire mapping
  -> P2-B ReactEngine/EngineFactory 切换

P2-C RegistrationToken + Registry owner
  -> P2-D MCP 完整 schema/owner/result mapping
  -> P2-E Tool assembly 移入 Runtime
       -> P2-F SkillTool/CliCallback 归位

P2-G provider DTO 移入 Config/LLM + ProviderCatalog
  -> P2-H 24h cache / 3s deadline + Config 纯化
P2-I MCPConfig 移入 Config 并保持外部 JSON 结构
P2-J 删除 MemoryProtocol/AgentMemory 预留

P2-B + P2-H + P2-J -> P2-K 删除 src/types
P2-D + P2-F + P2-I + P2-K -> P2-L import-boundary + package SCC 门禁
                      -> P2-M 文档/example/schema/ADR 同步
```

每个节点独立 PR，修改 2-10 个文件。超过 10 个文件时按“契约引入 / adapter 切换 / 旧代码清理”继续拆分。

## 19. PRD 追踪矩阵

| PRD ID | 技术章节 | ADR | DAG |
|--------|----------|-----|-----|
| P0-01 | 6.3, 7.2 | Core Tool Contracts | P0-B |
| P0-02 | 5.1, 6.1-6.2 | Core Tool Contracts | P0-A, P0-B |
| P0-03 | 6.3 | Core Tool Contracts | P0-C |
| P0-04 | 12.1 | Conversation/Transaction | P0-F |
| P0-05 | 5.1, 5.3, 6.2, 14 | Core Tool Contracts, Conversation/Transaction | P0-A, P0-D, P0-E, P1-G |
| P0-06 | 9.2, 12 | Conversation/Transaction, ProviderCatalog | P0-G - P0-J |
| P0-07 | 12.2, 17.1 | Conversation/Transaction | P0-K |
| P1-01 | 8, 14 | Conversation/Transaction | P1-F, P1-K |
| P1-02 | 5.1, 8.1, 9 | Conversation/Transaction | P1-F, P1-G |
| P1-03 | 9 | Conversation/Transaction | P1-H |
| P1-04 | 9 | Conversation/Transaction | P1-I |
| P1-05 | 5.3, 9.2, 12.3 | Core Tool Contracts, Conversation/Transaction | P0-H, P1-I |
| P1-06 | 10.5, 11 | Conversation/Transaction | P1-G, P1-J |
| P1-07 | 10.1-10.2 | Conversation/Transaction | P1-A - P1-D |
| P1-08 | 10.3-10.5 | Conversation/Transaction | P1-E, P1-G |
| P1-09 | 8, 14.1 | Conversation/Transaction | P1-F, P1-K |
| P1-10 | 5.3, 9, 14 | Conversation/Transaction | P1-G - P1-K |
| P1-11 | 17.2 | Conversation/Transaction | P1-L |
| P2-01 | 5.1-5.2 | Core Tool Contracts | P0-A, P2-A, P2-B |
| P2-02 | 5.2, 13 | ProviderCatalog | P2-A, P2-B, P2-G, P2-H |
| P2-03 | 4.1, 7.1 | Core Tool Contracts | P2-E |
| P2-04 | 4.1, 7.1, 15 | Core Tool Contracts | P2-F |
| P2-05 | 10.2, 15 | Core Tool Contracts, Conversation/Transaction | P1-B, P1-C, P2-E, P2-L |
| P2-06 | 13 | ProviderCatalog | P2-G, P2-H |
| P2-07 | 13 | ProviderCatalog | P2-G, P2-H |
| P2-08 | 7.2 | Core Tool Contracts | P2-D |
| P2-09 | 7.1 | Core Tool Contracts | P2-C, P2-D |
| P2-10 | 4.1, 5.2, 13 | Core Tool Contracts, ProviderCatalog | P2-A, P2-B, P2-G, P2-H, P2-J, P2-K |
| P2-11 | 4.1, 14.2, 15 | Core Tool Contracts | P2-F |
| P2-12 | 15 | 全部 | P2-L |
| P2-13 | 14.3, 17.3, 20 | 全部 | P2-M |
| P2-14 | 4.1, 20 | Core Tool Contracts, Conversation/Transaction | P2-J |

## 20. ADR 兼容性

| 现有 ADR | 保留 | 被新 ADR 补充或取代 |
|----------|------|----------------------|
| ADR 0001 | 75% 阈值、确定性 summary、稳定 instruction prefix | 增加 source IDs、success-time persistence plan 和原子替换 |
| ADR 0002 | 单一配置文件、插值和 Pydantic | Provider catalog 移出 Config，MCP 配置类型化 |
| ADR 0003 | fnmatch、last-match-wins、allow/ask/deny | PathPolicy 硬边界、fail-closed、CliCallback 归 CLI |
| ADR 0004 | Skill 格式、扫描优先级、按需加载 | SkillTool 归 Tools，Skill 装配归 Runtime |
| ADR 0005 | DB -> Service -> Tool 三层 | 显式 TurnContext 取代可变 conversation provider；移除 AgentMemory 预留 |
| ADR 0006 | SRP、DI、Repository 按表拆分、CLI 拆分 | Service 拥有事务，Tool assembly 归 Runtime，Core-owned ToolSpec |
| ADR 0007 | PyQt5、qasync、mistune、事件内容 | 取代“GUI 零修改 Core/Runtime/DB”、Core AsyncGenerator 直连、同步 PermissionDialog.exec 和 QFluentWidgets，GUI 改依赖应用层 |

## 21. 备选方案

### 21.1 AgentRuntime 直接承担 Conversation API

优点：少一个类。缺点：再次让 Runtime 同时承担 composition、生命周期、CRUD、active 状态和调度，重现 ADR 0006
已识别的问题。不采用。

### 21.2 Runtime PermissionedToolGateway

优点：Core port 更少。缺点：安全策略落入 Runtime，入口可绕过 gateway，违背“Core owns safety rules”。不采用。

### 21.3 每个 Conversation 常驻 actor

优点：支持多个会话并行。缺点：接近 Agent Worker/Bus，增加跨 session 调度和资源所有权，超出单 active Conversation 范围。
不采用。

## 22. 回滚与发布约束

- P0/P1/P2 每个节点独立回滚；基础契约只能在下游逆序回滚后撤销。
- SQLite schema 变化前提示备份/删除开发数据库；Git revert 不恢复已删除本地数据。
- P0-K warning 门禁最后启用，避免已知 warning 阻塞前置修复。
- P2 import-boundary 门禁在所有包迁移完成后启用。
- 自动化流程终点为合并，不包含 release。

# 技术方案: agent-team

**日期:** 2026-06-24
**状态:** Draft

## 1. 需求概述

### 1.1 问题描述
多 Agent 协作场景中，各 Agent 需要感知彼此身份、直接通信、查询通讯录。需要一个轻量级的 Agent 间通信基础设施，基于 SQLite 持久化，通过 6 个内置 tool 暴露能力。

### 1.2 目标用户/场景
- **运行中的 Agent 实例**：通过内置 tool 调用 `send_message`、`receive_message`、`get_contacts`、`get_contact_detail`
- **系统管理员**：通过 `create_agent`、`delete_agent` 管理 Agent 生命周期

### 1.3 成功标准
- 6 个内置 tool 的 TDD 实现并通过测试
- SQLite WAL 模式持久化，重启数据不丢失
- 消息写入 < 10ms，列表查询 < 50ms
- 代码架构清晰：db 层 / service 层 / tool 层边界明确

---

## 2. 技术栈

| 层级 | 技术选型 | 理由 |
|------|---------|------|
| 数据库 | SQLite (WAL 模式) + 标准库 `sqlite3` | PRD 约束：无 ORM，纯标准库；与现有 SQLAlchemy 表共存于同一文件 |
| 上下文注入 | `contextvars.ContextVar` | 标准库，asyncio 安全，与现有 `task_tools.set_task_context()` 模式一脉相承 |
| Tool 实现 | 异步函数 → JSON 字符串 | 遵循现有 `src/tools/` 约定（`success_response` / `error_response`） |
| ID 生成 | `uuid.uuid4()` | 标准库，避免现有 `_next_msg_id()` 的全局锁模式 |
| 时间格式 | ISO 8601 字符串 (`datetime.utcnow().isoformat()`) | PRD 要求，与现有模型一致 |
| 测试 | pytest + monkeypatch + 临时 SQLite 文件 | 遵循项目测试惯例 |

---

## 3. 架构设计

### 3.1 系统架构图

```
                          ┌─────────────────────────┐
                          │     AgentRuntime        │
                          │  set_agent_team_context  │
                          │  (db_path, agent_id)     │
                          └───────────┬─────────────┘
                                      │ 注入上下文
                                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                      ToolRegistry (_default_registry)            │
│                                                                  │
│  send_message ──── receive_message ──── get_contacts             │
│  get_contact_detail ──── create_agent ──── delete_agent          │
│                                                                  │
│  每个 tool 内部通过 _agent_team_ctx.get() 获取上下文              │
└──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                   src/core/agent_team.py (Service 层)            │
│                                                                  │
│  AgentTeamService                                                │
│  ├── send_message(sender_id, to_agent_id, content) → MessageResult│
│  ├── receive_message(receiver_id, limit, offset, unread_only)   │
│  ├── get_contacts(current_agent_id, status_filter)              │
│  ├── get_contact_detail(agent_id)                               │
│  ├── create_agent(name, desc, prompt)                           │
│  ├── delete_agent(agent_id)                                     │
│  └── 业务校验：Agent 存在性、同名冲突、参数合法性               │
└──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                  src/db/agent_team_db.py (DB 层)                 │
│                                                                  │
│  AgentTeamDB                                                     │
│  ├── init_db() → 建表 + WAL 模式 + 索引                          │
│  ├── insert_agent() / get_agent() / list_agents() / delete_agent()│
│  ├── insert_message() / list_messages() / mark_as_read()         │
│  └── 纯标准库 sqlite3，同步 API                                   │
└──────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
                           ┌─────────────────┐
                           │  intelliagent.db │
                           │  (SQLite WAL)    │
                           │                 │
                           │  agents         │
                           │  agent_messages │
                           └─────────────────┘
```

### 3.2 模块划分

| 模块 | 文件 | 职责 | 依赖 |
|------|------|------|------|
| **DB 层** | `src/db/agent_team_db.py` | 纯 sqlite3 CRUD：建表、插入、查询、更新 | 标准库 `sqlite3` |
| **Service 层** | `src/core/agent_team.py` | 业务逻辑封装：校验 Agent 存在性、同名检查、消息收发规则 | `src/db/agent_team_db.py` |
| **Tool 层** | `src/tools/agent_team_tools.py` | 6 个 tool 函数 + 上下文注入（`set_agent_team_context`）| `src/core/agent_team.py`、`src/tools/response.py` |
| **运行时集成** | `src/runtime/agent_runtime.py`（修改）| 在 `create_engine()` 时调用 `set_agent_team_context()` | `src/tools/agent_team_tools.py` |

### 3.3 数据流向

```
LLM 调用 tool (send_message)
  → ToolRegistry.call_tool("send_message", to_agent_id="bob", content="hello")
  → agent_team_tools.send_message(to_agent_id="bob", content="hello")
  → _agent_team_ctx.get() 获取 (db_path, current_agent_id)
  → AgentTeamService.send_message(sender_id=current_agent_id, to_agent_id="bob", content="hello")
  → AgentTeamDB.insert_message(...)
  → 返回 JSON: {"status":"ok","message_id":"uuid","created_at":"..."}
```

---

## 4. 接口设计

### 4.1 Tool 列表

#### T1: send_message
- **参数**：`to_agent_id: str`（必填）、`content: str`（必填）
- **返回**：`{"status":"ok","message_id":"<uuid>","created_at":"<iso8601>"}`
- **错误**：
  - `AGENT_NOT_FOUND` — 目标 Agent 不存在
  - `EMPTY_CONTENT` — 消息内容为空
  - `CONTEXT_NOT_INITIALIZED` — 未注入 Agent Team 上下文

#### T2: receive_message
- **参数**：`limit: int = 20`、`offset: int = 0`、`unread_only: bool = False`
- **返回**：`{"status":"ok","messages":[{...}],"total":42}`
- **行为**：查询当前 Agent 的收件箱，自动将返回的消息标记为已读
- **错误**：`CONTEXT_NOT_INITIALIZED`

#### T3: get_contacts
- **参数**：`status: str | None = None`（可选筛选：online / offline / busy）
- **返回**：`{"status":"ok","contacts":[{...}]}`
- **行为**：返回所有 Agent（排除当前 Agent），支持按状态过滤
- **错误**：`CONTEXT_NOT_INITIALIZED`、`INVALID_STATUS`（状态值不合法）

#### T4: get_contact_detail
- **参数**：`agent_id: str`（必填）
- **返回**：`{"status":"ok","agent":{...}}`
- **错误**：`AGENT_NOT_FOUND`

#### T5: create_agent
- **参数**：`name: str`（必填）、`desc: str = ""`、`prompt: str = ""`
- **返回**：`{"status":"ok","agent":{...}}`
- **错误**：`DUPLICATE_NAME`（同名 Agent 已存在）
- **注意**：ID 自动生成（UUID），不在参数中暴露

#### T6: delete_agent
- **参数**：`agent_id: str`（必填）
- **返回**：`{"status":"ok","deleted":true}`
- **行为**：删除 Agent 记录，不级联删除消息（保留历史）
- **错误**：`AGENT_NOT_FOUND`

### 4.2 数据模型

#### agents 表

```sql
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    desc        TEXT DEFAULT '',
    prompt      TEXT DEFAULT '',
    status      TEXT DEFAULT 'offline' CHECK(status IN ('online','offline','busy')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

#### agent_messages 表

```sql
CREATE TABLE IF NOT EXISTS agent_messages (
    id          TEXT PRIMARY KEY,
    sender_id   TEXT NOT NULL REFERENCES agents(id),
    receiver_id TEXT NOT NULL REFERENCES agents(id),
    content     TEXT NOT NULL,
    is_read     INTEGER DEFAULT 0 CHECK(is_read IN (0, 1)),
    created_at  TEXT NOT NULL
);

-- 收件箱查询索引（覆盖 receiver_id + is_read + created_at 排序）
CREATE INDEX IF NOT EXISTS idx_agent_messages_inbox
    ON agent_messages(receiver_id, is_read, created_at DESC);

-- 发送方查询索引
CREATE INDEX IF NOT EXISTS idx_agent_messages_sender
    ON agent_messages(sender_id, created_at DESC);
```

#### Agent 字典结构（DB 层返回）

```python
{
    "id": "agent-uuid-xxxx",
    "name": "CodeReviewer",
    "desc": "代码审查 Agent",
    "prompt": "你是一个代码审查专家...",
    "status": "online",
    "created_at": "2026-06-24T12:00:00",
    "updated_at": "2026-06-24T12:00:00",
}
```

#### Message 字典结构（DB 层返回）

```python
{
    "id": "msg-uuid-xxxx",
    "sender_id": "agent-uuid-aaaa",
    "sender_name": "Architect",         # JOIN agents 获得
    "receiver_id": "agent-uuid-bbbb",
    "content": "请审查 src/core/engine.py",
    "is_read": 1,
    "created_at": "2026-06-24T12:05:00",
}
```

---

## 5. DB 层接口（AgentTeamDB）

```python
class AgentTeamDB:
    """纯标准库 sqlite3，同步 API。调用方负责线程安全。"""

    def __init__(self, db_path: str) -> None:
        """打开连接，设置 WAL 模式、外键约束。"""

    def init_db(self) -> None:
        """建表 + 索引（幂等，IF NOT EXISTS）。"""

    # Agent CRUD
    def insert_agent(self, id: str, name: str, desc: str, prompt: str,
                     status: str, created_at: str, updated_at: str) -> dict:
        ...

    def get_agent(self, agent_id: str) -> dict | None:
        ...

    def get_agent_by_name(self, name: str) -> dict | None:
        ...

    def list_agents(self, exclude_id: str | None = None,
                    status_filter: str | None = None) -> list[dict]:
        """列出所有 Agent，可按状态过滤，可排除指定 ID。"""

    def delete_agent(self, agent_id: str) -> bool:
        """返回 True 表示删除成功，False 表示 Agent 不存在。"""

    # Message CRUD
    def insert_message(self, id: str, sender_id: str, receiver_id: str,
                       content: str, created_at: str) -> dict:
        ...

    def list_messages(self, receiver_id: str, limit: int, offset: int,
                      unread_only: bool) -> tuple[list[dict], int]:
        """返回 (消息列表, 总数)，消息列表含 sender_name（JOIN agents）。"""

    def mark_as_read(self, message_ids: list[str]) -> None:
        """批量标记已读。"""

    def close(self) -> None:
        ...
```

---

## 6. Service 层接口（AgentTeamService）

```python
class AgentTeamService:
    """封装业务逻辑：校验、错误码映射。"""

    def __init__(self, db: AgentTeamDB) -> None: ...

    def send_message(self, sender_id: str, to_agent_id: str,
                     content: str) -> dict:
        """
        Returns: {"id": ..., "created_at": ...}
        Raises: AgentNotFoundError, EmptyContentError
        """

    def receive_message(self, receiver_id: str, limit: int, offset: int,
                        unread_only: bool) -> tuple[list[dict], int]:
        """Returns: (消息列表, 总数)。自动标记已读。"""

    def get_contacts(self, current_agent_id: str,
                     status_filter: str | None) -> list[dict]:
        """排除当前 Agent。"""

    def get_contact_detail(self, agent_id: str) -> dict:
        """Raises: AgentNotFoundError"""

    def create_agent(self, name: str, desc: str, prompt: str) -> dict:
        """Raises: DuplicateNameError"""

    def delete_agent(self, agent_id: str) -> bool:
        """Raises: AgentNotFoundError"""
```

---

## 7. Tool 层接口（agent_team_tools.py）

```python
# 上下文注入 — 对标 task_tools.set_task_context() 模式
def set_agent_team_context(db_path: str | None, agent_id: str | None) -> None:
    """由 AgentRuntime 在创建 Engine 时调用。"""

# 6 个 tool 函数签名
async def send_message(to_agent_id: str, content: str) -> str: ...

async def receive_message(limit: int = 20, offset: int = 0,
                          unread_only: bool = False) -> str: ...

async def get_contacts(status: str | None = None) -> str: ...

async def get_contact_detail(agent_id: str) -> str: ...

async def create_agent(name: str, desc: str = "",
                       prompt: str = "") -> str: ...

async def delete_agent(agent_id: str) -> str: ...
```

---

## 8. 关键决策

### D1: 上下文注入 — ContextVar vs 全局变量
**选择**：`contextvars.ContextVar`，`set_agent_team_context()` 模式
**理由**：
- 与现有 `task_tools.set_task_context()` 模式一致
- `contextvars` 是标准库，asyncio 安全，无数据泄漏风险
- 不修改 `ToolRegistry` 和 `ReactEngine` 接口
- Tool 函数内部通过 `_ctx.get()` 获取，上下文缺失时返回 `CONTEXT_NOT_INITIALIZED`

### D2: DB 层 — 纯 sqlite3（同步）vs 现有 SQLAlchemy
**选择**：纯标准库 sqlite3，同步 API
**理由**：
- PRD 明确要求"无 ORM，使用标准库 sqlite3"
- agent-team 的数据表（agents、agent_messages）与现有 ORM 表（conversations、messages、tasks）在语义和生命周期上完全独立
- 同步 sqlite3 在 Python 3.12+ 中性能足够（< 10ms 写入）
- 避免引入 aiosqlite 新依赖（且 agent-team 不需要 SQLAlchemy 的关系映射能力）
- 独立 db 模块不破坏现有 ORM 层

### D3: Tool 函数风格 — 同步 vs 异步
**选择**：异步函数（`async def`）
**理由**：与现有所有 tool 函数保持一致，`ToolRegistry.call_tool()` 使用 `await tool.function(**kwargs)`

### D4: Agent ID 生成策略
**选择**：`uuid.uuid4()` 生成，不在参数中暴露
**理由**：
- Agent ID 应全局唯一且不可预测
- `create_agent` 的参数只包含 name/desc/prompt，ID 由 Service 层生成
- 与现有 `_next_msg_id()` 不同：Agent 不需要单调递增的 ID

### D5: 消息 ID 生成策略
**选择**：`uuid.uuid4()` 
**理由**：
- 消息 ID 只需唯一性，不需要排序语义
- 排序由 `created_at` 字段保证
- 避免全局锁竞争（现有 `_next_msg_id` 使用 threading.Lock）

### D6: 接收消息的"自动标记已读"语义
**行为**：`receive_message` 返回的消息**自动标记为已读**，不提供"保留未读"选项
**理由**：PRD US-2 验收标准明确"接收消息时自动将消息标记为已读"，无保留未读的需求

### D7: Agent 删除行为
**选择**：仅逻辑删除 Agent 记录（软删除：status = 'deleted'），消息保留
**理由**：
- PRD 要求"不级联删除消息，保留历史" → `DELETE` 会因为外键约束报错（agent_messages 引用 agents），但 PRD 说无级联
- 实际需要做的是：由于 agent_messages 表有 `REFERENCES agents(id)`，必须使用 `ON DELETE SET NULL` 或不做 FK 约束
- **最终决定**：agent_messages 的外键不加 `ON DELETE CASCADE`，也不设 `ON DELETE SET NULL`。Agent 删除时使用 SQLite 的 `PRAGMA foreign_keys = ON` 环境下的直接 DELETE——如果 agent 有消息记录，delete 会失败。替代方案：
  - **方案 A（推荐）**：不做真正的外键约束，仅在应用层校验。表定义中使用普通 TEXT 字段，不加 REFERENCES。
  - **方案 B**：使用 `ON DELETE SET NULL`，但 sender_id/receiver_id 为 NULL 会破坏查询语义。
  - **方案 C**：Agent 做软删除（status='deleted'），保留记录。
  
  **推荐方案 C**：软删除。Agent 删除后将 status 设为 'deleted'，不再出现在通讯录中（`get_contacts` 过滤 status != 'deleted'），但历史消息中的 sender_id/receiver_id 仍然有效。

---

## 9. 实施计划

### 子任务拆分及执行顺序

| 序号 | 任务 | 产出文件 | 验收标准 | 预估时间 |
|------|------|---------|---------|---------|
| **S1** | DB 层实现 | `src/db/agent_team_db.py` | `pytest tests/db/test_agent_team_db.py` 通过：建表/插入/查询/索引 | 30min |
| **S2** | Service 层实现 | `src/core/agent_team.py` | `pytest tests/core/test_agent_team_service.py` 通过：6 种业务场景全覆盖 | 45min |
| **S3** | Tool 层实现 | `src/tools/agent_team_tools.py` | `pytest tests/tools/test_agent_team_tools.py` 通过：6 个 tool 的 JSON 输入/输出验证 | 45min |
| **S4** | Tool 注册 | 修改 `src/tools/registry.py` | 6 个 tool 出现在 `get_openai_tools()` 中 | 15min |
| **S5** | 运行时集成 | 修改 `src/runtime/agent_runtime.py` | 集成测试通过：AgentRuntime 创建 Engine 后 tool 可用 | 15min |

**执行顺序**：S1 → S2 → S3 → S4 → S5（严格依赖链）

### 风险点及对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 从异步 tool 中调用同步 sqlite3 导致事件循环阻塞 | 性能下降 | sqlite3 同步写入 < 1ms，无需异步；如果未来成为瓶颈，使用 `asyncio.to_thread` 或 `aiosqlite` 包装 |
| agent_messages 外键与软删除 Agent 冲突 | 删除 Agent 时消息 sender_id 失效 | 采用软删除方案（status='deleted'），不做物理删除 |
| 现有 db 模块（SQLAlchemy）与新增 agent_team_db（sqlite3）并存导致连接管理混乱 | 两个独立连接写入同一 SQLite 文件可能冲突 | WAL 模式下读并发安全；两个模块使用独立连接，各自打开关闭，写操作由 SQLite 内部 WAL 锁管理 |
| ContextVar 未设置时 tool 被调用 | Tool 返回 CONTEXT_NOT_INITIALIZED 错误 | 在 tool 入口第一行检查，返回明确错误码，LLM 可据此提示用户初始化 |

---

## 10. 非功能需求实现方案

### 10.1 性能

| 指标 | 目标 | 实现方案 |
|------|------|---------|
| 消息写入 < 10ms | 纯 sqlite3 INSERT | 同步写入，无网络开销；WAL 模式下写不阻塞读 |
| 列表查询 < 50ms | 覆盖索引 + LIMIT/OFFSET | `idx_agent_messages_inbox(receiver_id, is_read, created_at DESC)` 覆盖收件箱查询全字段 |
| 并发读 | WAL 模式 | 初始化时 `PRAGMA journal_mode=WAL` |

### 10.2 安全

| 措施 | 实现 |
|------|------|
| 当前 Agent ID 不可伪造 | 由 `set_agent_team_context()` 注入，tool 参数不包含 sender_id |
| 消息发送方校验 | sender_id 由 ContextVar 获取，无法通过 tool 参数覆盖 |
| 无内部 API 暴露 | 所有能力仅通过 ToolRegistry 注册的 tool 接口暴露 |

### 10.3 可用性

| 措施 | 实现 |
|------|------|
| 幂等初始化 | `CREATE TABLE IF NOT EXISTS`，多次调用 `init_db()` 无副作用 |
| 优雅降级 | 上下文未注入时返回明确错误码 `CONTEXT_NOT_INITIALIZED`，而非抛异常 |
| 连接管理 | AgentTeamDB 实例生命周期由调用方管理，支持 `close()` 显式释放 |

---

## 11. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `src/db/agent_team_db.py` | **新建** | 纯 sqlite3 的 Agent + Message 持久化层 |
| `src/core/agent_team.py` | **新建** | Service 层：业务逻辑 + 校验 |
| `src/tools/agent_team_tools.py` | **新建** | 6 个 tool 实现 + set_agent_team_context |
| `src/tools/registry.py` | **修改** | 新增 6 个 tool 注册（在 `_default_registry` 初始化段末尾） |
| `src/runtime/agent_runtime.py` | **修改** | `create_engine()` 中调用 `set_agent_team_context()` |
| `tests/db/test_agent_team_db.py` | **新建** | DB 层测试 |
| `tests/core/test_agent_team_service.py` | **新建** | Service 层测试 |
| `tests/tools/test_agent_team_tools.py` | **新建** | Tool 层测试 |

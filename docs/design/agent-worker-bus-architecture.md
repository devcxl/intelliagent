# 技术方案: Agent Worker + Bus 架构

**日期:** 2026-06-25
**状态:** Draft
**替代:** [agent-team 旧方案](./agent-team.md)

---

## 1. 问题陈述

### 1.1 当前架构的根本缺陷

当前架构把 **Conversation（会话）** 作为第一公民，Agent 是从属的：

```
ConversationOrchestrator（入口）
  └─ setup_conversation()
       └─ ReactEngine（一次性消耗品）
            └─ run(task) → 结束
```

这导致两个问题：

1. **单 Agent 和多 Agent 互斥** — `ConversationOrchestrator` 只能管一个会话，无法表达"多个 Agent 同时运行，各自拥有独立会话"的语义。
2. **Agent 没有生命周期** — Agent 只是一条 DB 记录（`agents` 表），创建后没有运行实例，`send_message` 写入 `agent_messages` 后无人消费。

### 1.2 目标架构

**Agent 是第一公民，Conversation 是 Agent Worker 的内部细节。**

```
AgentBus（全局单例，消息路由 + Worker 管理）
  ├─ AgentWorker("main-agent")    # 主 Agent，等 stdin
  ├─ AgentWorker("analyst")       # 子 Agent，等消息队列
  ├─ AgentWorker("reviewer")      # 子 Agent，等消息队列
  └─ ...

每个 AgentWorker 独立持有：
  ├─ ReactEngine（自己的 LLM 上下文）
  ├─ ToolRegistry（按白名单过滤）
  ├─ Conversation（按需创建/恢复，不再由 Orchestrator 管控）
  └─ 消息处理循环
```

### 1.3 两种启动模式

```
# 模式 A：主 Agent（用户交互）
python -m src.cli.main interactive
  └─ 启动 AgentBus
       ├─ 注册所有 Agent 配置（从 DB 或配置文件）
       ├─ 启动所有 Worker
       ├─ 主 Agent 的 Worker 进入 REPL 循环（读 stdin）
       └─ 子 Agent 的 Worker 进入消息循环（等 queue）

# 模式 B：独立 Worker（子 Agent 单独进程）
python -m src.cli.main worker --agent-id analyst
  └─ 启动 AgentBus
       ├─ 只注册自己
       ├─ 启动自己的 Worker
       └─ Worker 进入消息循环（等 queue）
```

---

## 2. 核心概念

### 2.1 概念层次

```
Agent（配置实体）
  │
  ├── id: str              # 唯一标识
  ├── name: str            # 名称
  ├── prompt: str          # 系统提示词
  ├── model: str           # 使用的模型
  ├── tools: list[str]     # 允许的工具白名单
  └── status: str          # 生命周期状态（inactive | active | deleted）

AgentWorker（运行时实例）
  │
  ├── config: Agent         # 对应的 Agent 配置
  ├── engine: ReactEngine   # 独立的 ReAct 引擎
  ├── queue: asyncio.Queue  # 消息信箱
  ├── task: asyncio.Task    # 运行中的协程
  │
  └── async def _loop():    # 主循环
        while True:
          msg = await queue.get()
          engine.add_message(msg.content)
          result = await engine.continue_loop()
          await bus.send_reply(...)

AgentBus（全局单例，消息路由 + Worker 管理）
  │
  ├── workers: dict[str, AgentWorker]
  ├── db: DatabaseSession
  │
  ├── register(Agent) → AgentWorker
  ├── start_all() → 启动所有 Worker 协程
  ├── send_message(sender, receiver, content) → 写 DB + 推送队列
  └── shutdown()

Conversation（降级为查询视图）
  │
  ├── 不再是入口概念
  ├── Worker 内部按需创建/恢复
  └── MessageRepository.list_by_conversation() 仍然可用
```

### 2.2 和旧 agent-team 方案的关键区别

| | 旧方案 (agent-team) | 新方案 (worker-bus) |
|---|---|---|
| 第一公民 | Conversation | Agent |
| Agent 运行时 | 无（只有 DB 记录） | AgentWorker（持有 ReactEngine） |
| 消息消费 | 无人消费 | Worker 循环主动消费 |
| 消息通信 | 纯 DB 写入 | DB 持久化 + 内存队列推送 |
| 工具集 | 6 个工具全部暴露 | 只保留 `send_message`（精简） |
| 入口 | 单一 `main.py` | 两个入口：`interactive` / `worker` |
| ConversationOrchestrator | 全局入口 | 降级为 Worker 内部工具 |

---

## 3. 架构图

```
┌──────────────────────────────────────────────────────────────────────┐
│                            main.py                                    │
│                                                                       │
│  python -m src.cli.main interactive      python -m src.cli.main worker │
│  ──────────────────────────────          ─────────────────────────    │
│                                                                       │
└──────────────┬──────────────────────────────────┬─────────────────────┘
               │                                  │
               ▼                                  ▼
┌──────────────────────────────┐   ┌──────────────────────────────────┐
│        AgentBus              │   │         AgentBus                  │
│                              │   │                                  │
│  workers: {                  │   │  workers: {                      │
│    "main": Worker(...),      │   │    "analyst": Worker(...),       │
│    "analyst": Worker(...),   │   │  }                               │
│    "reviewer": Worker(...),  │   │                                  │
│  }                           │   │                                  │
│                              │   │                                  │
│  register()                  │   │  register()                      │
│  start_all()                 │   │  start_all()                     │
│  send_message()              │   │  send_message()                  │
│  shutdown()                  │   │  shutdown()                      │
└──────┬───────────────────────┘   └────────────┬─────────────────────┘
       │                                        │
       │  ┌─────────────────────────────────┐   │
       └──►         AgentWorker             ◄───┘
          │                                 │
          │  config: Agent                  │
          │  engine: ReactEngine            │
          │  queue: asyncio.Queue           │
          │  task: asyncio.Task             │
          │                                 │
          │  async _loop():                 │
          │    msg = await queue.get()      │
          │    engine.continue(msg)         │
          │    result = await engine._loop()│
          │    bus.send_reply(result)       │
          └────────────┬────────────────────┘
                       │
                       ▼
          ┌────────────────────────┐
          │     ReactEngine         │
          │                        │
          │  messages: [...]       │  ← 自己的上下文（不共享）
          │  tools: ToolRegistry   │  ← 按白名单过滤
          │  permission: ...       │
          │  skills: ...           │
          └────────────┬───────────┘
                       │
                       ▼
          ┌────────────────────────┐
          │   DB (SQLite / WAL)     │
          │                        │
          │  agents                │  ← Agent 配置（prompt, tools, model）
          │  agent_messages        │  ← 消息队列（sender, receiver, status）
          │  conversations         │  ← Worker 的会话（降级为查询视图）
          │  messages              │  ← Worker 的对话历史
          │  tasks                 │  ← Worker 的任务列表
          └────────────────────────┘
```

---

## 4. 数据模型

### 4.1 agents 表（Agent 配置）

```sql
CREATE TABLE agents (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    desc          TEXT DEFAULT '',
    prompt        TEXT DEFAULT '',
    model         TEXT DEFAULT '',           -- 新增：使用的模型
    tools         TEXT DEFAULT '[]',         -- 新增：允许的工具白名单（JSON 数组）
    status        TEXT DEFAULT 'inactive'    -- 修改：inactive | active | deleted
                     CHECK(status IN ('inactive', 'active', 'deleted')),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
```

### 4.2 agent_messages 表（消息队列）

```sql
CREATE TABLE agent_messages (
    id              TEXT PRIMARY KEY,
    sender_id       TEXT NOT NULL,
    receiver_id     TEXT NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT DEFAULT 'pending'   -- 新增：pending | processing | done | failed
                        CHECK(status IN ('pending', 'processing', 'done', 'failed')),
    correlation_id  TEXT,                    -- 新增：关联 ID（用于追踪任务-回复关系）
    reply_to_id     TEXT,                    -- 新增：回复哪条消息
    error           TEXT,                    -- 新增：失败原因
    created_at      TEXT NOT NULL,
    claimed_at      TEXT,                    -- 新增：被 Worker 认领时间
    completed_at    TEXT                     -- 新增：处理完成时间
);

CREATE INDEX idx_agent_messages_receiver_status
    ON agent_messages(receiver_id, status, created_at DESC);
```

### 4.3 旧表保留不变

`conversations`、`messages`、`tasks` 三张表不动。Worker 内部用 `ConversationRepository` / `MessageRepository` / `TaskRepository` 管理自己的会话。

---

## 5. 核心接口

### 5.1 AgentBus

```python
class AgentBus:
    """全局单例。管理所有 AgentWorker 实例，负责消息路由。"""

    def __init__(self, db_session_factory, llm_client_factory, permission_factory):
        self._workers: dict[str, AgentWorker] = {}
        self._db = db_session_factory
        self._llm_factory = llm_client_factory
        self._permission_factory = permission_factory

    async def register(self, config: AgentConfig) -> AgentWorker:
        """注册一个 Agent 配置，创建对应的 Worker 实例。不启动。"""
        worker = AgentWorker(config, self._db, self._llm_factory, self._permission_factory)
        self._workers[config.id] = worker
        return worker

    async def start_all(self) -> None:
        """启动所有已注册的 Worker 协程。"""
        for worker in self._workers.values():
            await worker.start()

    async def send_message(
        self,
        sender_id: str,
        receiver_id: str,
        content: str,
        correlation_id: str | None = None,
        reply_to_id: str | None = None,
    ) -> dict:
        """
        发送消息：
        1. 写入 agent_messages 表（status=pending）
        2. 如果 receiver 的 Worker 在本地池中，推送到其内存队列
        返回消息记录
        """
        ...

    async def shutdown(self) -> None:
        """停止所有 Worker，清理资源。"""
        ...
```

### 5.2 AgentWorker

```python
class AgentWorker:
    """单个 Agent 的运行时实例。持有独立的 ReactEngine 和消息队列。"""

    def __init__(self, config, db, llm_factory, permission_factory):
        self.config = config
        self._engine: ReactEngine | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._conversation_id: str | None = None

    async def start(self) -> None:
        """启动 Worker 的消息处理循环（创建 asyncio.Task）。"""
        self._engine = self._build_engine()
        self._task = asyncio.create_task(self._loop())

    def notify(self, message: dict) -> None:
        """外部推送消息到本 Worker 的队列。"""
        self._queue.put_nowait(message)

    async def _loop(self) -> None:
        """主循环：阻塞等待消息 → 处理 → 回复 → 循环。"""
        while True:
            msg = await self._queue.get()
            try:
                await self._process_message(msg)
            except Exception:
                ...

    async def _process_message(self, msg: dict) -> None:
        """
        处理单条消息：
        1. 标记消息为 processing
        2. 加载/恢复 Conversation（首次自动创建）
        3. 将消息内容作为 user message 追加到 engine
        4. 运行 ReactEngine
        5. 将结果写回 agent_messages（reply）
        6. 标记原消息为 done
        """
        ...

    async def _load_or_create_conversation(self, sender_id: str) -> str:
        """加载与 sender 的对话历史，无历史则创建新 Conversation。"""
        ...

    def _build_engine(self) -> ReactEngine:
        """根据 Agent 配置构建 ReactEngine。"""
        ...

    async def shutdown(self) -> None:
        """停止 Worker，清理资源。"""
        ...
```

### 5.3 ReactEngine 改动

```python
class ReactEngine:
    # 新增参数
    def __init__(self, ..., system_prompt: str | None = None):
        self._system_prompt = system_prompt  # 覆盖默认 prompt

    # 新增方法：在已有 messages 末尾追加一条消息，继续跑循环
    async def continue_with_message(self, content: str) -> dict:
        """不重置 messages，追加 user message 后继续 _loop()。"""
        self.add_user_message(content)
        return await self._loop()

    # run() 保留不动，用于首次执行
```

### 5.4 Tool 层改动

只保留一个工具：

```python
# send_message — 唯一保留的 agent-team 工具
async def send_message(to_agent_name: str, content: str) -> str:
    """
    向指定 Agent 发送消息。
    通过 AgentBus 写入 DB 并推送目标 Worker 队列。
    立即返回，不等待结果。
    """
    ...
```

删掉的 5 个工具：`receive_message`、`get_contacts`、`get_contact_detail`、`create_agent`、`delete_agent`。

---

## 6. 启动流程

### 6.1 主 Agent 模式（用户交互）

```
python -m src.cli.main interactive

1. 加载 intelliagent.json
2. 创建 AgentBus（注入 db, llm, permission 工厂）
3. 从 agents 表（或配置文件）加载所有 Agent 配置
4. 逐个 bus.register(config)
5. bus.start_all()
   ├─ main_agent_worker.start()  → 进入 stdin REPL 循环
   ├─ analyst_worker.start()     → 进入消息循环（await queue.get()）
   └─ reviewer_worker.start()    → 进入消息循环（await queue.get()）
6. 用户输入 → main_agent_worker 处理 → 可能调用 send_message → 子 Worker 被唤醒
7. Ctrl+C → bus.shutdown()
```

### 6.2 独立 Worker 模式

```
python -m src.cli.main worker --agent-id analyst

1. 加载 intelliagent.json
2. 创建 AgentBus
3. 从 agents 表加载 agent_id="analyst" 的配置
4. bus.register(analyst_config)
5. bus.start_all()
   └─ analyst_worker.start() → 进入消息循环
6. 消息循环：
   ├─ 优先从 agent_messages 表 claim pending 消息（启动时可能有积压）
   ├─ 然后 await queue.get()（等待实时推送）
   └─ 处理 → 回复 → 循环
7. SIGTERM → bus.shutdown()
```

### 6.3 消息处理完整流程

```
主 Agent 调用 send_message("analyst", "分析 data.csv")

1. send_message tool:
   ├─ AgentBus.send_message("main", "analyst", "分析 data.csv")
   │   ├─ DB: INSERT agent_messages (status=pending)
   │   └─ bus._workers["analyst"].notify(msg)
   └─ 返回 {"status": "ok", "message_id": "..."}

2. analyst_worker._queue.get() 被唤醒

3. analyst_worker._process_message(msg):
   ├─ DB: UPDATE agent_messages SET status='processing', claimed_at=now
   ├─ 加载/创建 Conversation（如 conv-analyst-main）
   ├─ engine.add_user_message("分析 data.csv")
   ├─ 加载历史上下文（MessageRepository.list_by_conversation）
   ├─ result = await engine._loop()
   ├─ DB: INSERT agent_messages (sender="analyst", receiver="main",
   │       content=result.answer, reply_to_id=msg.id)
   └─ DB: UPDATE agent_messages SET status='done', completed_at=now
```

---

## 7. 文件变更

### 7.1 新增文件

| 文件 | 说明 |
|------|------|
| `src/agent/__init__.py` | 包初始化 |
| `src/agent/bus.py` | `AgentBus` 实现 |
| `src/agent/worker.py` | `AgentWorker` 实现 |
| `src/agent/config.py` | `AgentConfig` 数据模型 |
| `docs/design/agent-worker-bus-architecture.md` | 本文档 |

### 7.2 修改文件

| 文件 | 改动 |
|------|------|
| `src/core/react_engine.py` | 加 `system_prompt` 参数、加 `continue_with_message()` |
| `src/tools/agent_team_tools.py` | 只保留 `send_message`，删掉其余 5 个 |
| `src/tools/registry.py` | 反注册 5 个多余工具 |
| `src/db/models.py` | `AgentMessage` 加 `status`/`correlation_id`/`reply_to_id`/`error` 字段 |
| `src/db/repositories.py` | 加 `claim_next()`/`mark_done()`/`create_reply()` |
| `src/cli/main.py` | 新增 `interactive` 和 `worker` 子命令 |
| `src/cli/parser.py` | 新增子命令解析 |
| `src/runtime/conversation_orchestrator.py` | 降级为工具类（不再做入口） |

### 7.3 删除文件

| 文件 | 原因 |
|------|------|
| `src/core/agent_team.py` | 被 `src/agent/bus.py` + `src/agent/worker.py` 替代 |

### 7.4 不动文件

| 文件 | 原因 |
|------|------|
| `src/core/react_engine.py` | 只加参数和方法，核心循环不变 |
| `src/llm/` | 不变 |
| `src/tools/file_tools.py` | 不变 |
| `src/tools/task_tools.py` | 不变 |
| `src/tools/shell_tool.py` | 不变 |
| `src/config/` | 不变 |
| `src/permission/` | 不变 |
| `src/skills/` | 不变 |
| `src/mcp/` | 不变 |
| `src/db/models.py` (Conversation/Message/Task) | 不变 |

---

## 8. 关键决策

### D1: 消息通信 — DB + 内存队列双写

**选择**：`send_message` 同时写入 DB 和推送内存队列。
**理由**：
- DB 持久化：进程重启后消息不丢失
- 内存队列：同进程内的 Worker 无需轮询 DB，即时唤醒
- 跨进程场景（独立 Worker 进程）：内存队列不可用，Worker 启动时从 DB claim pending 消息

### D2: Worker 的 Conversation 管理

**选择**：每个 Worker 内部按需创建 Conversation，key 为 `(worker_id, 对方 agent_id)` 的组合。
**理由**：
- 主 Agent 和每个子 Agent 各有一组对话
- Worker 重启时从 DB 恢复历史上下文
- 不引入新的全局概念

### D3: 删掉 5 个 agent-team 工具

**选择**：只保留 `send_message`，删掉 `receive_message`/`get_contacts`/`get_contact_detail`/`create_agent`/`delete_agent`。
**理由**：
- `receive_message`：Worker 自动处理，不需要 LLM 手动查收件箱
- `get_contacts`/`get_contact_detail`：Agent 配置是系统级的，不需要 LLM 动态查询
- `create_agent`/`delete_agent`：属于管理操作，不应通过 LLM tool 暴露

### D4: AgentBus 是单例还是实例

**选择**：实例（非全局单例），由 main.py 创建并持有。
**理由**：
- 测试时不需要重置全局状态
- 一个进程内可以有多个 Bus（如测试场景）
- 与项目现有风格一致（无全局单例）

### D5: Worker 空闲策略

**选择**：Worker 一直运行，`await queue.get()` 阻塞等待。
**理由**：
- 协程阻塞不消耗 CPU
- 不需要 TTL 驱逐、懒加载等复杂逻辑
- 启动即全部在线，模型简单

---

## 9. 实施计划

### 阶段 1：数据模型 + 仓储

1. 修改 `src/db/models.py` — `AgentMessage` 加字段
2. 修改 `src/db/repositories.py` — 加队列方法
3. 测试：DB 层单元测试

### 阶段 2：AgentBus + AgentWorker

1. 新建 `src/agent/config.py`
2. 新建 `src/agent/bus.py`
3. 新建 `src/agent/worker.py`
4. 测试：用 fake engine 测试 Worker 消息消费

### 阶段 3：ReactEngine 改动

1. `src/core/react_engine.py` — 加 `system_prompt` + `continue_with_message()`
2. 测试：引擎单元测试

### 阶段 4：Tool 精简 + CLI

1. 删掉 5 个多余工具
2. `send_message` 接入 AgentBus
3. `src/cli/main.py` 新增 `interactive` / `worker` 子命令
4. `src/cli/parser.py` 新增子命令解析
5. 集成测试：主 Agent 发消息 → 子 Agent 处理 → 回复

### 阶段 5：清理

1. 删除 `src/core/agent_team.py`
2. 降级 `ConversationOrchestrator`
3. 更新 `CONTEXT.md` 和 ADR

---

## 10. 风险

| 风险 | 对策 |
|------|------|
| Worker 崩溃后消息丢失 | 消息在 DB 中持久化，重启时 claim pending 消息恢复 |
| 同进程内多个 Worker 同时操作 DB | SQLite WAL 模式支持并发读，写操作串行化（SQLite 内部锁） |
| 子 Agent 也调 send_message 形成循环调用 | AgentBus 可检测调用链深度，超过阈值拒绝 |
| ReactEngine 不支持"追加消息后继续" | `continue_with_message()` 是小改动，核心循环不变 |

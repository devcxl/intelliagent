# ADR 0005: Agent Team 架构

## 状态

已实施（T1~T3），T4~T5 待完成

## 背景

需要支持多 Agent 间的通信与协作，使 Agent 能够像团队一样工作——互相发送消息、查询通讯录、创建/删除 Agent。这为未来的 Agent 编排、任务分配和并行执行奠定基础。

## 决策

采用三层架构（DB → Service → Tool），使用纯 `sqlite3`（而非 SQLAlchemy）实现 Agent 专属存储，通过 `ContextVar` 注入当前 Agent 身份。

## 详细设计

### 三层架构

```
Tool Layer (6 个 agent-team tools)
    ↓
Service Layer (AgentTeamService, 6 种业务逻辑)
    ↓
DB Layer (AgentTeamDB, 纯 sqlite3, WAL 模式)
```

### 表结构

```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    prompt TEXT DEFAULT '',
    status TEXT DEFAULT 'online',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    from_agent_id TEXT NOT NULL,
    to_agent_id TEXT NOT NULL,
    content TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
```

### 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据库 | 纯 sqlite3 | 避免循环依赖（SQLAlchemy 模型在 src/db/ 中） |
| 上下文 | ContextVar | 避免显式传参，tool 函数无需感知 DB 连接 |
| ID 生成 | uuid4 | 分布式友好，无需自增 |
| 软删除 | status=deleted | 保留历史消息引用完整性 |

### 模块集成

```python
# AgentRuntime.create_engine() 中
set_agent_team_context(db_path, agent_id)
```

## 理由

- **避免循环依赖**：纯 sqlite3 不依赖 SQLAlchemy，`src/core/agent_team.py` 可独立测试
- **ContextVar 隐式注入**：tool 函数签名保持简洁，无需透传 DB session
- **uuid4 ID**：Agent 可能在不同进程或机器创建，自增 ID 不适合分布式场景
- **软删除**：历史消息可能引用已删除的 Agent，保留记录避免级联删除

## 后果

- 两个数据库并存：主库（SQLAlchemy ORM）和 Agent Team 库（纯 sqlite3）
- 数据库路径通过 `UnifiedConfig.database.url` 解析，需 `_resolve_agent_team_db_path()` 桥接
- 当前仅支持单机模式，不支持跨进程 Agent 通信

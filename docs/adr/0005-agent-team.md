# ADR 0005: Agent Team 架构

## 状态

已实施，作为可选能力默认关闭。

## 背景

需要支持多 Agent 间的通信与协作，使 Agent 能够像团队一样工作——互相发送消息、查询通讯录、创建/删除 Agent。这为未来的 Agent 编排、任务分配和并行执行奠定基础。

## 决策

采用三层架构（SQLAlchemy DB Model/Repository → Service → Tool Adapter），复用主 SQLite 数据库。Agent Team 通过 `agent_team.enabled` 配置显式启用，默认不注册到工具列表。

## 详细设计

### 三层架构

```
Tool Adapter Layer (6 个 agent-team tools)
    ↓
Service Layer (AgentTeamService, 6 种业务逻辑)
    ↓
Repository Layer (AgentRepository / RelayRepository)
    ↓
DB Layer (SQLAlchemy models: Agent / Relay / AgentMemory)
```

### 表结构

```sql
-- 真实定义以 src/db/models.py 为准。
-- Agent: agents 表，保存名称、描述、prompt、工具、模型、工作区和状态。
-- Relay: relays 表，保存 sender_id、receiver_id、content、is_read。
-- AgentMemory: agent_memories 表，当前为预留模型，不在运行链路中启用。
```

### 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据库 | 主库 SQLAlchemy models/repositories | 避免维护第二套数据库访问层 |
| 启用方式 | `agent_team.enabled=false` 默认关闭 | 保持默认 coding-agent skeleton 轻量 |
| 依赖注入 | `AgentTeamTools(session_factory_provider, agent_id)` | 避免全局状态和隐式 ContextVar |
| ID 生成 | uuid4 | 分布式友好，无需自增 |
| 软删除 | status=deleted | 保留历史消息引用完整性 |

### 模块集成

```python
# AgentRuntime._create_tool_registry() 中
ToolRegistryFactory(
    session_factory_provider=self._database_runtime.get_session_factory,
    conversation_id_provider=lambda: self.conversation_id,
    agent_id=self._config.agent_id,
    agent_team_enabled=self._config.agent_team.enabled,
)
```

当 `agent_team.enabled` 为 `false` 时，默认工具列表不包含 `send_message`、`receive_message`、`get_contacts`、`get_contact_detail`、`create_agent`、`delete_agent`。

## 理由

- **复用主库**：Agent Team 数据与 conversation/task 数据共享同一个数据库运行时，生命周期由 `DatabaseRuntime` 管理
- **显式启用**：默认不增加模型可见工具数量，符合 skeleton 项目定位
- **显式依赖注入**：tool adapter 持有 session factory 和当前 agent id，避免全局上下文
- **uuid4 ID**：Agent 可能在不同进程或机器创建，自增 ID 不适合分布式场景
- **软删除**：历史消息可能引用已删除的 Agent，保留记录避免级联删除

## 后果

- Agent Team schema 仍在主 DB metadata 中创建，但工具默认不注册
- 启用后会增加 6 个模型可见工具
- 当前仅支持单机模式，不支持跨进程 Agent 通信

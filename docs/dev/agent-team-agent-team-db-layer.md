# 开发文档: T1 — DB 层实现

**Project:** agent-team
**Task ID:** T1
**Slug:** agent-team-db-layer
**Issue:** #20
**类型:** backend
**Batch:** 1
**依赖:** 无

---

## 1. 目标

实现 `AgentTeamDB` 类：纯标准库 `sqlite3` 的 Agent + Message 持久化层。提供建表、Agent CRUD、Message CRUD 能力，作为 agent-team 功能栈的最底层模块。

---

## 2. 前置条件

- 无（第一批任务，无上游依赖）
- Python 3.12+（标准库 `sqlite3` 即可，无额外依赖）
- 了解技术方案 `docs/design/agent-team.md`（特别是 §4.2 数据模型、§5 DB 层接口、§8 关键决策 D2/D7）

---

## 3. 实现步骤

### 3.1 新建 `src/db/agent_team_db.py`

**文件:** `src/db/agent_team_db.py`

**关键约束（必须遵守）：**
- **不使用 ORM / SQLAlchemy**，纯标准库 `sqlite3`
- **`agent_messages` 表不使用外键约束**（`REFERENCES`），存在性校验由后续 Service 层负责
- Agent 删除采用**软删除**：`UPDATE agents SET status = 'deleted', updated_at = ?`
- 所有方法为**同步** API（不涉及 `async`/`await`）
- 调用方负责线程安全（`AgentTeamDB` 自身不做线程同步）

#### 3.1.1 类结构

```python
import sqlite3
from pathlib import Path


class AgentTeamDB:
    """纯标准库 sqlite3，同步 API。调用方负责线程安全。"""

    def __init__(self, db_path: str) -> None:
        """
        打开连接，启用 WAL 模式 + 外键约束。

        Args:
            db_path: SQLite 数据库文件路径（如 "/path/to/intelliagent.db"）。
                     如果目录不存在则自动创建。
        """

    def init_db(self) -> None:
        """建表 + 索引（幂等，IF NOT EXISTS）。"""

    # ── Agent CRUD ──────────────────────────────────────────

    def insert_agent(
        self,
        id: str,
        name: str,
        desc: str,
        prompt: str,
        status: str,
        created_at: str,
        updated_at: str,
    ) -> dict:
        """插入新 Agent，返回完整 dict。"""

    def get_agent(self, agent_id: str) -> dict | None:
        """按 ID 查询 Agent，不存在返回 None。"""

    def get_agent_by_name(self, name: str) -> dict | None:
        """按 name 查询 Agent（用于同名检查），不存在返回 None。"""

    def list_agents(
        self,
        exclude_id: str | None = None,
        status_filter: str | None = None,
    ) -> list[dict]:
        """
        列出 Agent，支持：
        - 排除指定 ID（用于通讯录排除当前 Agent）
        - 按 status 过滤（如 'online'、'busy'）
        默认不过滤 status='deleted'（由 Service 层决定是否排除）。
        """

    def delete_agent(self, agent_id: str) -> bool:
        """
        软删除 Agent：将 status 设为 'deleted'，更新 updated_at。
        返回 True 表示更新成功（更新了 1 行），False 表示 Agent 不存在（0 行）。
        """

    # ── Message CRUD ────────────────────────────────────────

    def insert_message(
        self,
        id: str,
        sender_id: str,
        receiver_id: str,
        content: str,
        created_at: str,
    ) -> dict:
        """插入新消息，返回完整 dict（不含 sender_name，需后续 JOIN）。"""

    def list_messages(
        self,
        receiver_id: str,
        limit: int,
        offset: int,
        unread_only: bool = False,
    ) -> tuple[list[dict], int]:
        """
        查询收件箱消息，返回 (消息列表, 总数)。

        消息列表每项含 sender_name（LEFT JOIN agents），
        按 created_at DESC 排序。
        当 unread_only=True 时只返回 is_read=0 的消息。
        """

    def mark_as_read(self, message_ids: list[str]) -> None:
        """批量标记已读：UPDATE agent_messages SET is_read = 1 WHERE id IN (...)。"""

    # ── 生命周期 ────────────────────────────────────────────

    def close(self) -> None:
        """关闭数据库连接。"""
```

#### 3.1.2 `__init__` 实现细节

```python
def __init__(self, db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(str(path))
    self._conn.row_factory = sqlite3.Row       # 按列名访问
    self._conn.execute("PRAGMA journal_mode=WAL")
    self._conn.execute("PRAGMA foreign_keys=ON")
```

- `row_factory = sqlite3.Row` — 查询结果可通过列名访问（`row["id"]`），转换为 dict 时使用 `dict(row)`
- WAL 模式 — 写不阻塞读，支持并发读
- `foreign_keys=ON` — 虽然 agent_messages 不设 FK，但保留此设置以备后续扩展

#### 3.1.3 `init_db` 实现细节

```python
def init_db(self) -> None:
    self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL UNIQUE,
            desc        TEXT DEFAULT '',
            prompt      TEXT DEFAULT '',
            status      TEXT DEFAULT 'offline'
                CHECK(status IN ('online', 'offline', 'busy', 'deleted')),
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_messages (
            id          TEXT PRIMARY KEY,
            sender_id   TEXT NOT NULL,
            receiver_id TEXT NOT NULL,
            content     TEXT NOT NULL,
            is_read     INTEGER DEFAULT 0 CHECK(is_read IN (0, 1)),
            created_at  TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_agent_messages_inbox
            ON agent_messages(receiver_id, is_read, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_agent_messages_sender
            ON agent_messages(sender_id, created_at DESC);
    """)
```

**DDL 说明：**
| 设计项 | 值 | 依据 |
|--------|-----|------|
| `agents.name` UNIQUE | ✅ 添加 `UNIQUE` 约束 | 支持同名检查（`get_agent_by_name`），也防止 DB 层插入同名 |
| `agents.status` 允许值 | `online`, `offline`, `busy`, `deleted` | 软删除方案要求 `deleted` 作为合法状态 |
| `agent_messages` 无外键 | ✅ 纯 TEXT，无 `REFERENCES` | 设计决策 D7：应用层校验存在性，避免 FK 与软删除冲突 |
| `PRAGMA journal_mode=WAL` | ✅ 在 `__init__` 设置 | D2：WAL 模式支持并发读，写不阻塞读 |
| `PRAGMA foreign_keys=ON` | ✅ 在 `__init__` 设置 | 保留以备后续扩展；当前表无 FK，此设置不影响 agent_messages |

> ⚠️ **与 `agent-team.md` §4.2 DDL 的差异**：技术方案中 DDL 写有 `REFERENCES agents(id)`，但任务图 §S1 关键约束明确要求"agent_messages 表不使用外键约束"。本处 DDL 为**实现权威版本**。

#### 3.1.4 Agent CRUD 实现要点

**`insert_agent`**:
```python
def insert_agent(self, id, name, desc, prompt, status, created_at, updated_at):
    self._conn.execute(
        "INSERT INTO agents (id, name, desc, prompt, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (id, name, desc, prompt, status, created_at, updated_at),
    )
    self._conn.commit()
    return self.get_agent(id)  # 返回完整记录
```

**`get_agent`**:
```python
def get_agent(self, agent_id):
    row = self._conn.execute(
        "SELECT * FROM agents WHERE id = ?", (agent_id,)
    ).fetchone()
    return dict(row) if row else None
```

**`get_agent_by_name`**:
```python
def get_agent_by_name(self, name):
    row = self._conn.execute(
        "SELECT * FROM agents WHERE name = ?", (name,)
    ).fetchone()
    return dict(row) if row else None
```

**`list_agents`**:
```python
def list_agents(self, exclude_id=None, status_filter=None):
    query = "SELECT * FROM agents WHERE 1=1"
    params = []

    if exclude_id is not None:
        query += " AND id != ?"
        params.append(exclude_id)

    if status_filter is not None:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY name ASC"
    rows = self._conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
```

**`delete_agent`** (软删除):
```python
def delete_agent(self, agent_id):
    now = ...  # ISO 8601 当前时间
    cur = self._conn.execute(
        "UPDATE agents SET status = 'deleted', updated_at = ? WHERE id = ?",
        (now, agent_id),
    )
    self._conn.commit()
    return cur.rowcount > 0
```

#### 3.1.5 Message CRUD 实现要点

**`insert_message`**:
```python
def insert_message(self, id, sender_id, receiver_id, content, created_at):
    self._conn.execute(
        "INSERT INTO agent_messages (id, sender_id, receiver_id, content, is_read, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (id, sender_id, receiver_id, content, created_at),
    )
    self._conn.commit()
    # 返回不含 sender_name（与 list_messages 不同），后续 Service 层可自行组装
    return {
        "id": id,
        "sender_id": sender_id,
        "receiver_id": receiver_id,
        "content": content,
        "is_read": 0,
        "created_at": created_at,
    }
```

**`list_messages`** (关键方法 — JOIN agents 获取 sender_name):
```python
def list_messages(self, receiver_id, limit, offset, unread_only=False):
    base_query = """
        SELECT m.id, m.sender_id, m.receiver_id, m.content,
               m.is_read, m.created_at, a.name AS sender_name
        FROM agent_messages m
        LEFT JOIN agents a ON a.id = m.sender_id
        WHERE m.receiver_id = ?
    """
    params = [receiver_id]

    if unread_only:
        base_query += " AND m.is_read = 0"

    # 先查总数（不带 LIMIT/OFFSET）
    count_query = f"SELECT COUNT(*) FROM ({base_query})"
    total = self._conn.execute(count_query, params).fetchone()[0]

    # 再查分页数据
    data_query = f"{base_query} ORDER BY m.created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = self._conn.execute(data_query, params).fetchall()

    return [dict(row) for row in rows], total
```

**`mark_as_read`**:
```python
def mark_as_read(self, message_ids):
    if not message_ids:
        return
    placeholders = ",".join("?" * len(message_ids))
    self._conn.execute(
        f"UPDATE agent_messages SET is_read = 1 WHERE id IN ({placeholders})",
        message_ids,
    )
    self._conn.commit()
```

#### 3.1.6 `close` 实现

```python
def close(self) -> None:
    self._conn.close()
```

---

### 3.2 新建 `tests/db/test_agent_team_db.py`

**文件:** `tests/db/test_agent_team_db.py`

**测试基础设施：**
- 使用 pytest 的 `tmp_path` fixture 创建临时 SQLite 文件
- 每个测试独立创建 `AgentTeamDB` 实例，测试后 `close()`
- 可使用 pytest fixture 封装 DB 初始化逻辑以减少重复代码

#### 3.2.1 测试分类

| 测试类 | 测试场景 | 预期结果 |
|--------|---------|---------|
| `TestInitDB` | 建表幂等性 | |
| | `init_db()` 调用一次 | agents 和 agent_messages 表存在 |
| | `init_db()` 调用两次 | 不抛异常，表结构不变 |
| | 索引存在性 | `idx_agent_messages_inbox` 和 `idx_agent_messages_sender` 存在 |
| `TestAgentCRUD` | Agent 全生命周期 | |
| | `insert_agent()` → `get_agent()` | 返回的 dict 包含所有字段，值与插入一致 |
| | `get_agent_by_name()` 存在 | 返回完整 dict |
| | `get_agent_by_name()` 不存在 | 返回 `None` |
| | `list_agents()` 无过滤 | 返回所有 Agent，按 name ASC 排序 |
| | `list_agents(exclude_id=...)` | 排除指定 Agent |
| | `list_agents(status_filter='online')` | 只返回 online 的 Agent |
| | `delete_agent()` 存在 | 返回 `True`，status 变为 'deleted'，updated_at 更新 |
| | `delete_agent()` 不存在 | 返回 `False` |
| | 软删除后 `get_agent()` | Agent 仍可查询（status='deleted'） |
| `TestMessageCRUD` | Message 全生命周期 | |
| | `insert_message()` → `list_messages()` | 返回的消息包含 sender_name（JOIN agents） |
| | `list_messages(unread_only=True)` | 只返回 is_read=0 的消息 |
| | `mark_as_read()` | 消息 is_read 变为 1 |
| | `list_messages()` 排序 | 按 created_at DESC 排序 |
| | `list_messages()` 分页 | LIMIT/OFFSET 正确 |
| | `list_messages()` 总数 | 返回值 total 正确 |
| `TestEdgeCases` | 边界条件 | |
| | `get_agent("nonexistent")` | 返回 `None` |
| | `mark_as_read([])` | 不抛异常 |
| | 插入相同 id 的 Agent | `sqlite3.IntegrityError`（主键冲突） |
| | 插入相同 name 的 Agent | `sqlite3.IntegrityError`（UNIQUE 冲突） |
| | 插入 status 不合法 | `sqlite3.IntegrityError`（CHECK 约束） |
| | WAL 模式验证 | `PRAGMA journal_mode` 返回 `"wal"` |

#### 3.2.2 测试 fixture 示例

```python
import pytest
import sqlite3
from src.db.agent_team_db import AgentTeamDB


@pytest.fixture
def db(tmp_path):
    """创建临时 SQLite 数据库并初始化。"""
    db_path = tmp_path / "test_agent_team.db"
    agent_db = AgentTeamDB(str(db_path))
    agent_db.init_db()
    yield agent_db
    agent_db.close()
```

---

## 4. 接口/契约

### 4.1 `AgentTeamDB` 完整方法签名

```python
class AgentTeamDB:
    def __init__(self, db_path: str) -> None
    def init_db(self) -> None

    # Agent CRUD
    def insert_agent(self, id: str, name: str, desc: str, prompt: str,
                     status: str, created_at: str, updated_at: str) -> dict
    def get_agent(self, agent_id: str) -> dict | None
    def get_agent_by_name(self, name: str) -> dict | None
    def list_agents(self, exclude_id: str | None = None,
                    status_filter: str | None = None) -> list[dict]
    def delete_agent(self, agent_id: str) -> bool

    # Message CRUD
    def insert_message(self, id: str, sender_id: str, receiver_id: str,
                       content: str, created_at: str) -> dict
    def list_messages(self, receiver_id: str, limit: int, offset: int,
                      unread_only: bool = False) -> tuple[list[dict], int]
    def mark_as_read(self, message_ids: list[str]) -> None

    # 生命周期
    def close(self) -> None
```

### 4.2 数据模型 (DDL)

#### `agents` 表

```sql
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    desc        TEXT DEFAULT '',
    prompt      TEXT DEFAULT '',
    status      TEXT DEFAULT 'offline'
        CHECK(status IN ('online', 'offline', 'busy', 'deleted')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
```

#### `agent_messages` 表

```sql
CREATE TABLE IF NOT EXISTS agent_messages (
    id          TEXT PRIMARY KEY,
    sender_id   TEXT NOT NULL,
    receiver_id TEXT NOT NULL,
    content     TEXT NOT NULL,
    is_read     INTEGER DEFAULT 0 CHECK(is_read IN (0, 1)),
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_messages_inbox
    ON agent_messages(receiver_id, is_read, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_messages_sender
    ON agent_messages(sender_id, created_at DESC);
```

### 4.3 返回值数据形状

#### Agent dict（`get_agent` / `insert_agent` / `get_agent_by_name` / `list_agents` 返回）

```python
{
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "CodeReviewer",
    "desc": "代码审查 Agent",
    "prompt": "你是代码审查专家...",
    "status": "online",
    "created_at": "2026-06-24T12:00:00.000000",
    "updated_at": "2026-06-24T12:00:00.000000",
}
```

#### Message dict（`list_messages` 返回）

```python
{
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "sender_id": "agent-uuid-aaaa",
    "sender_name": "Architect",       # LEFT JOIN agents 获得
    "receiver_id": "agent-uuid-bbbb",
    "content": "请审查 src/core/engine.py",
    "is_read": 1,
    "created_at": "2026-06-24T12:05:00.000000",
}
```

#### Message dict（`insert_message` 返回）

```python
{
    "id": "660e8400-e29b-41d4-a716-446655440001",
    "sender_id": "agent-uuid-aaaa",
    "receiver_id": "agent-uuid-bbbb",
    "content": "请审查 src/core/engine.py",
    "is_read": 0,
    "created_at": "2026-06-24T12:05:00.000000",
}
# 注意：insert_message 不返回 sender_name（无 JOIN），
# sender_name 仅在 list_messages 中通过 LEFT JOIN 获取。
```

---

## 5. 测试指引

### 5.1 测试文件组织

```
tests/db/
└── test_agent_team_db.py
    ├── TestInitDB
    │   ├── test_create_tables_on_first_init
    │   ├── test_init_is_idempotent
    │   └── test_indexes_exist
    ├── TestAgentCRUD
    │   ├── test_insert_and_get_agent
    │   ├── test_get_agent_by_name_found
    │   ├── test_get_agent_by_name_not_found
    │   ├── test_list_agents_all
    │   ├── test_list_agents_exclude_id
    │   ├── test_list_agents_status_filter
    │   ├── test_delete_agent_success
    │   ├── test_delete_agent_not_found
    │   └── test_soft_deleted_agent_still_queryable
    ├── TestMessageCRUD
    │   ├── test_insert_and_list_message
    │   ├── test_list_messages_unread_only
    │   ├── test_list_messages_sort_order
    │   ├── test_list_messages_pagination
    │   ├── test_list_messages_total_count
    │   ├── test_mark_as_read
    │   └── test_list_messages_includes_sender_name
    └── TestEdgeCases
        ├── test_get_agent_nonexistent
        ├── test_mark_as_read_empty_list
        ├── test_insert_duplicate_id
        ├── test_insert_duplicate_name
        ├── test_insert_invalid_status
        └── test_wal_mode_enabled
```

### 5.2 测试模板

```python
from __future__ import annotations

import pytest
from src.db.agent_team_db import AgentTeamDB


class TestInitDB:

    def test_create_tables_on_first_init(self, db):
        """init_db() 调用后表应存在。"""
        tables = db._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        assert "agents" in table_names
        assert "agent_messages" in table_names

    def test_init_is_idempotent(self, db):
        """两次 init_db() 不抛异常。"""
        db.init_db()  # 不应抛异常
```

### 5.3 运行测试

```bash
# 运行 DB 层全部测试
pytest tests/db/test_agent_team_db.py -v

# 运行特定测试类
pytest tests/db/test_agent_team_db.py::TestInitDB -v
```

---

## 6. 验收标准

- [ ] `pytest tests/db/test_agent_team_db.py` 全部通过（预期 ~20 个测试用例）
- [ ] 覆盖：建表幂等性、Agent CRUD 全路径、Message CRUD 全路径、索引有效性、软删除语义、边界条件
- [ ] `AgentTeamDB` 不依赖 SQLAlchemy、aiosqlite 或任何第三方 ORM
- [ ] `agent_messages` 表无外键约束（`sqlite_master` 中无 `FOREIGN KEY` 子句）
- [ ] WAL 模式生效（`PRAGMA journal_mode` 返回 `wal`）
- [ ] 代码通过 `ruff check` 和 `ruff format` 检查

---

## 7. 注意事项

### 7.1 关键约束（不可违反）

| # | 约束 | 来源 |
|---|------|------|
| 1 | 不使用 ORM / SQLAlchemy，纯 `sqlite3` | PRD 约束 + D2 |
| 2 | `agent_messages` 不使用外键约束 | 任务图 S1 关键约束 + D7 |
| 3 | Agent 删除用软删除（`status='deleted'`） | D7 最终决定 |
| 4 | 同步 API（不涉及 async/await） | D2 |
| 5 | DB 不负责 ID 生成（由 Service 层生成 UUID） | D4/D5 |

### 7.2 与现有代码的关系

- `src/db/agent_team_db.py` 与现有 `src/db/models.py`（SQLAlchemy ORM 模型）**完全独立**，各自管理自己的表
- 两者共享同一个 SQLite 文件（`intelliagent.db`），WAL 模式下读并发安全
- `src/db/__init__.py` 暂不导出 `AgentTeamDB`（待 T4/T5 集成时添加）

### 7.3 供下游（T2 Service 层）参考

T2 的 `AgentTeamService` 将：
- 通过构造函数接收 `AgentTeamDB` 实例
- 负责生成 UUID（`uuid.uuid4()`）和时间戳（`datetime.utcnow().isoformat()`）
- 负责业务校验（Agent 存在性、同名冲突、content 非空）
- `AgentTeamDB` 不做任何业务校验（纯数据访问层）

### 7.4 时间格式

所有 `created_at` / `updated_at` 使用 ISO 8601 字符串格式，推荐：
```python
from datetime import datetime, timezone
datetime.now(timezone.utc).isoformat()
# → "2026-06-24T12:00:00.000000+00:00"
```

或简化为不带时区的格式（与现有项目风格一致）：
```python
datetime.utcnow().isoformat()
# → "2026-06-24T12:00:00.000000"
```

两种格式均有效，建议与后续 Service 层协调统一。

# 开发文档: T2 - Service 层实现

**Project:** agent-team
**Task ID:** T2
**Slug:** agent-team-service-layer
**Issue:** #21
**类型:** backend
**Batch:** 2
**依赖:** T1 (agent-team-db-layer, #20)

---

## 1. 目标

实现 `AgentTeamService` 类，封装 agent-team 全部业务逻辑：校验、ID 生成、时间戳生成、软删除语义、同名冲突检查。为 T3 Tool 层提供可直接调用的同步 service 接口。

**核心职责：**
- 业务校验（Agent 存在性、消息内容非空、同名冲突、状态合法性）
- ID 生成（`uuid.uuid4()`）和时间戳生成（ISO 8601）
- 错误映射（Python 异常 → 错误码，供 Tool 层使用 `error_response()` 序列化）
- 软删除语义（`delete_agent` 将 status 设为 `'deleted'`，保留历史消息引用）

---

## 2. 前置条件

| 前提 | 状态 |
|------|------|
| T1 完成：`src/db/agent_team_db.py` 可用 | `AgentTeamDB` 类已实现并通过测试 |
| `uuid` 标准库 | Python 3.12+ 内置，无额外依赖 |
| `datetime` 标准库 | Python 3.12+ 内置，无额外依赖 |

**T1 交付的 DB 接口清单（Service 层直接依赖）：**

```
AgentTeamDB
├── insert_agent(id, name, desc, prompt, status, created_at, updated_at) → dict
├── get_agent(agent_id) → dict | None
├── get_agent_by_name(name) → dict | None
├── list_agents(exclude_id?, status_filter?) → list[dict]
├── delete_agent(agent_id) → bool          # 软删除: UPDATE status='deleted'
├── insert_message(id, sender_id, receiver_id, content, created_at) → dict
├── list_messages(receiver_id, limit, offset, unread_only) → tuple[list[dict], int]
│     # 消息字典包含 sender_name（DB 层 JOIN agents 获得）
├── mark_as_read(message_ids: list[str]) → None
└── close()
```

---

## 3. 模块设计

### 3.1 文件位置

```
src/core/agent_team.py          # Service 层（本任务）
tests/core/test_agent_team_service.py  # 单元测试
```

### 3.2 异常类设计

4 个自定义异常，位于 `src/core/agent_team.py` 顶部，继承自 `Exception`。每个异常携带错误码，供 Tool 层映射到 JSON error response。

```python
class AgentTeamError(Exception):
    """agent-team 业务异常基类。"""

class AgentNotFoundError(AgentTeamError):
    """Agent 不存在。"""
    code = "AGENT_NOT_FOUND"

class EmptyContentError(AgentTeamError):
    """消息内容为空。"""
    code = "EMPTY_CONTENT"

class DuplicateNameError(AgentTeamError):
    """同名 Agent 已存在。"""
    code = "DUPLICATE_NAME"

class InvalidStatusError(AgentTeamError):
    """状态值不合法。"""
    code = "INVALID_STATUS"
```

**设计决策：**
- 使用类属性 `code` 而非实例属性，简化 Tool 层错误码提取：`type(e).__dict__.get("code", "UNKNOWN_ERROR")`
- 统一继承 `AgentTeamError`，方便 Tool 层做 `except AgentTeamError as e:` 统一捕获
- 不需要 `message` 参数构造——错误描述在 Tool 层根据异常类型生成中文消息

### 3.3 AgentTeamService 类设计

```python
class AgentTeamService:
    """封装 agent-team 业务逻辑：校验、ID 生成、错误码映射。

    所有方法为同步调用。调用方负责传入正确的参数，Service 层
    不关心上下文注入或 tool 协议——这些由 Tool 层处理。
    """

    def __init__(self, db: AgentTeamDB) -> None:
        """注入 DB 层实例。"""
        self._db = db
```

#### 合法状态值常量

```python
_VALID_STATUSES = frozenset({"online", "offline", "busy", "deleted"})
```

`"deleted"` 包含在合法值集合中（`get_agent` 可能返回已删除 Agent），但 `get_contacts` 永远过滤 `status != 'deleted'`，`delete_agent` 也只能将 status 更新为 `'deleted'`。

---

## 4. 方法详细规格

### 4.1 send_message

```
send_message(sender_id: str, to_agent_id: str, content: str) → dict
```

**校验流程：**
1. `content.strip()` 为空 → `raise EmptyContentError()`
2. `self._db.get_agent(to_agent_id)` 返回 `None` → `raise AgentNotFoundError()`
3. （T1 已决定 agent_messages 表不加 FK，应用层校验接收方存在性）

**业务逻辑：**
1. 生成消息 ID：`str(uuid.uuid4())`
2. 生成时间戳：`datetime.now(timezone.utc).isoformat()`
3. 调用 `self._db.insert_message(id=msg_id, sender_id=sender_id, receiver_id=to_agent_id, content=content.strip(), created_at=created_at)`
4. 返回 `{"id": msg_id, "created_at": created_at}`

**返回值：**
```python
{"id": "msg-uuid-xxxx", "created_at": "2026-06-24T12:00:00.123456+00:00"}
```

**异常：**
| 条件 | 异常 |
|------|------|
| content 为空或纯空白 | `EmptyContentError` |
| to_agent_id 不存在或无权限 | `AgentNotFoundError` |

### 4.2 receive_message

```
receive_message(receiver_id: str, limit: int = 20,
                offset: int = 0, unread_only: bool = False) → tuple[list[dict], int]
```

**业务逻辑：**
1. 调用 `self._db.list_messages(receiver_id, limit, offset, unread_only)`
2. 获取返回的消息列表（含 `sender_name`），提取所有消息 ID
3. 如果有消息，调用 `self._db.mark_as_read(message_ids)` 批量标记已读
4. 返回 `(messages, total_count)`

**返回值：**
```python
(
    [
        {
            "id": "msg-uuid-xxxx",
            "sender_id": "agent-uuid-aaaa",
            "sender_name": "Architect",
            "receiver_id": "agent-uuid-bbbb",
            "content": "请审查 src/core/engine.py",
            "is_read": 1,       # 返回时已标记为已读
            "created_at": "2026-06-24T12:05:00.123456+00:00",
        },
        ...
    ],
    42,   # 符合查询条件的消息总数（不受 limit/offset 限制）
)
```

**行为保证：**
- 返回的消息的 `is_read` 字段在 DB 中已更新为 1
- `total_count` 是总数，不受 `limit`/`offset` 限制（但受 `unread_only` 影响）

### 4.3 get_contacts

```
get_contacts(current_agent_id: str, status_filter: str | None = None) → list[dict]
```

**校验流程：**
1. `status_filter` 不为 `None` 且不在 `{"online", "offline", "busy"}` 中 → `raise InvalidStatusError()`
   - 注意：`"deleted"` 不在可查询的状态中（通讯录不应包含已删除 Agent）

**业务逻辑：**
1. 调用 `self._db.list_agents(exclude_id=current_agent_id, status_filter=status_filter)`
   - DB 层负责过滤 `status != 'deleted'`，Service 层不做二次过滤
2. 返回 Agent 列表

**返回值：**
```python
[
    {
        "id": "agent-uuid-xxxx",
        "name": "CodeReviewer",
        "desc": "代码审查 Agent",
        "prompt": "...",         # 通讯录中暴露 prompt，供 Agent 了解彼此能力
        "status": "online",
        "created_at": "2026-06-24T12:00:00.123456+00:00",
        "updated_at": "2026-06-24T12:00:00.123456+00:00",
    },
    ...
]
```

**异常：**
| 条件 | 异常 |
|------|------|
| status_filter 不合法 | `InvalidStatusError` |

### 4.4 get_contact_detail

```
get_contact_detail(agent_id: str) → dict
```

**校验流程：**
1. `self._db.get_agent(agent_id)` 返回 `None` → `raise AgentNotFoundError()`

**业务逻辑：**
1. 直接返回 DB 查询结果（完整 Agent 字典）

**返回值：**
```python
{
    "id": "agent-uuid-xxxx",
    "name": "CodeReviewer",
    "desc": "代码审查 Agent",
    "prompt": "你是一个代码审查专家...",
    "status": "online",
    "created_at": "2026-06-24T12:00:00.123456+00:00",
    "updated_at": "2026-06-24T12:00:00.123456+00:00",
}
```

**异常：**
| 条件 | 异常 |
|------|------|
| agent_id 不存在 | `AgentNotFoundError` |

### 4.5 create_agent

```
create_agent(name: str, desc: str = "", prompt: str = "") → dict
```

**校验流程：**
1. `name.strip()` 为空 → `raise ValueError("Agent name is required")`（参数校验层，非业务异常）
2. `self._db.get_agent_by_name(name)` 不为 `None` → `raise DuplicateNameError()`

**业务逻辑：**
1. 生成 Agent ID：`str(uuid.uuid4())`
2. 生成时间戳：`now = datetime.now(timezone.utc).isoformat()`
3. 调用 `self._db.insert_agent(id=agent_id, name=name.strip(), desc=desc, prompt=prompt, status="offline", created_at=now, updated_at=now)`
4. 返回完整 Agent 字典

**返回值：**
```python
{
    "id": "agent-uuid-xxxx",
    "name": "CodeReviewer",
    "desc": "代码审查 Agent",
    "prompt": "你是一个代码审查专家...",
    "status": "offline",       # 新 Agent 默认离线
    "created_at": "2026-06-24T12:00:00.123456+00:00",
    "updated_at": "2026-06-24T12:00:00.123456+00:00",
}
```

**异常：**
| 条件 | 异常 |
|------|------|
| 同名 Agent 已存在 | `DuplicateNameError` |
| name 为空 | `ValueError` |

### 4.6 delete_agent

```
delete_agent(agent_id: str) → bool
```

**校验流程：**
1. `self._db.get_agent(agent_id)` 返回 `None` → `raise AgentNotFoundError()`

**业务逻辑：**
1. 调用 `self._db.delete_agent(agent_id)`（软删除：`UPDATE status='deleted'`）
2. 返回 `True`

**软删除保证：**
- Agent 记录保留，`status` 变为 `'deleted'`
- 历史消息中的 `sender_id`/`receiver_id` 仍然有效
- `get_contacts` 不再返回此 Agent（过滤 `status != 'deleted'`）
- 再次调用 `get_agent(agent_id)` 仍可获取（`status='deleted'`），供消息历史展示发送方名称

**异常：**
| 条件 | 异常 |
|------|------|
| agent_id 不存在 | `AgentNotFoundError` |

---

## 5. 实现步骤

### 5.1 新建 `src/core/agent_team.py`

**文件结构：**

```
src/core/agent_team.py
├── 导入区（uuid, datetime, typing）
├── 异常类定义（AgentTeamError 及 4 个子类）
├── _VALID_STATUSES 常量
└── AgentTeamService 类
    ├── __init__(db)
    ├── send_message(...)
    ├── receive_message(...)
    ├── get_contacts(...)
    ├── get_contact_detail(...)
    ├── create_agent(...)
    └── delete_agent(...)
```

**实现指引：**

1. **导入模块**：
   ```python
   from __future__ import annotations

   import uuid
   from datetime import datetime, timezone

   from src.db.agent_team_db import AgentTeamDB
   ```

2. **异常类**：按 3.2 节定义，每个子类覆盖 `code` 类属性。

3. **`__init__`**：仅保存 `self._db = db`。不做任何连接操作（连接由调用方管理）。

4. **`send_message`**：
   - 先校验 `content.strip()` 非空
   - 再校验目标 Agent 存在（两次校验顺序保证：先轻量校验，再查库）
   - 使用 `uuid.uuid4()` 生成 ID
   - 使用 `datetime.now(timezone.utc).isoformat()` 生成时间戳
   - 时间戳格式：`"2026-06-24T12:00:00.123456+00:00"`（含微秒 + 时区）

5. **`receive_message`**：
   - 直接透传参数给 DB 层
   - 提取返回的消息 ID 列表，调用 `mark_as_read`
   - 注意：`list_messages` 返回 `tuple[list[dict], int]`，解包使用 `messages, total = ...`

6. **`get_contacts`**：
   - `status_filter` 为 `None` 时不做额外校验，直接传给 DB 层（DB 层始终过滤 `status != 'deleted'`）
   - `status_filter` 不为 `None` 时检查合法性

7. **`get_contact_detail`**：单行校验 + 透传。

8. **`create_agent`**：
   - 先检查 name 非空（ValueError）
   - 再查重（DuplicateNameError）
   - 生成完整数据后插入

9. **`delete_agent`**：先检查存在性，再调用 DB 软删除。

### 5.2 新建 `tests/core/test_agent_team_service.py`

**目录不存在时需要先创建 `tests/core/` 目录和 `tests/core/__init__.py`。**

**测试架构：**

使用 **手动 fake 对象**（非 monkeypatch）替代 `AgentTeamDB`，因为 Service 层是同步代码且 DB 接口定义明确：

```python
class FakeAgentTeamDB:
    """在内存字典中模拟 AgentTeamDB 行为。"""
    def __init__(self):
        self.agents = {}       # {id: dict}
        self.messages = []     # [dict]
        self._name_index = {}  # {name: id}

    def get_agent(self, agent_id): ...
    def get_agent_by_name(self, name): ...
    def list_agents(self, exclude_id=None, status_filter=None): ...
    def insert_agent(self, ...): ...
    def delete_agent(self, agent_id): ...
    def insert_message(self, ...): ...
    def list_messages(self, receiver_id, limit, offset, unread_only): ...
    def mark_as_read(self, message_ids): ...
    def close(self): ...
```

**为什么用手动 fake 而非 monkeypatch：**
- `AgentTeamService` 方法数量少（6 个），fake DB 的"正确行为"易于验证
- 手动 fake 可精确控制返回值（如 `get_agent` 返回 `None` 模拟不存在，返回 dict 模拟存在）
- 避免 monkeypatch 的隐式行为（mock 的方法签名与实际不一致不会被检测到）
- 测试更易读：`service = AgentTeamService(fake_db)` 一行即可，无需 `monkeypatch.setattr(...)` 链

**测试用例清单（≥ 16 个）：**

| # | 测试方法 | 场景 | 预期 |
|---|---------|------|------|
| 1 | `test_send_message_success` | 正常发送 | 返回 `{id, created_at}`，消息写入 fake DB |
| 2 | `test_send_message_empty_content` | content 为空 | `EmptyContentError` |
| 3 | `test_send_message_whitespace_content` | content 纯空白 | `EmptyContentError` |
| 4 | `test_send_message_agent_not_found` | 目标 Agent 不存在 | `AgentNotFoundError` |
| 5 | `test_receive_message_success` | 正常收消息 | 返回 `(messages, total)`，消息已标记已读 |
| 6 | `test_receive_message_marks_as_read` | 收消息后自动标记已读 | `is_read` 全部变为 1 |
| 7 | `test_receive_message_with_limit_offset` | 分页查询 | 返回正确页的消息和总数 |
| 8 | `test_receive_message_unread_only` | 只查未读 | 仅返回 `is_read=0` 的消息 |
| 9 | `test_get_contacts_all` | 查询全部通讯录 | 排除当前 Agent，不包含 status='deleted' |
| 10 | `test_get_contacts_status_filter` | 按状态过滤 | 仅返回指定状态的 Agent |
| 11 | `test_get_contacts_invalid_status` | 非法状态值 | `InvalidStatusError` |
| 12 | `test_get_contact_detail_success` | 查询 Agent 详情 | 返回完整字典 |
| 13 | `test_get_contact_detail_not_found` | Agent 不存在 | `AgentNotFoundError` |
| 14 | `test_create_agent_success` | 正常创建 | 返回完整 Agent 字典，status='offline' |
| 15 | `test_create_agent_duplicate_name` | 同名冲突 | `DuplicateNameError` |
| 16 | `test_create_agent_empty_name` | name 为空 | `ValueError` |
| 17 | `test_delete_agent_success` | 正常软删除 | 返回 True，Agent status 变为 'deleted' |
| 18 | `test_delete_agent_not_found` | Agent 不存在 | `AgentNotFoundError` |
| 19 | `test_delete_agent_preserves_record` | 软删除后仍可查询 | `get_agent` 仍返回记录（status='deleted'） |

---

## 6. 接口/契约

### 6.1 Service 方法签名（完整）

```python
class AgentTeamService:
    def __init__(self, db: AgentTeamDB) -> None: ...

    def send_message(self, sender_id: str, to_agent_id: str,
                     content: str) -> dict: ...

    def receive_message(self, receiver_id: str, limit: int = 20,
                        offset: int = 0,
                        unread_only: bool = False) -> tuple[list[dict], int]: ...

    def get_contacts(self, current_agent_id: str,
                     status_filter: str | None = None) -> list[dict]: ...

    def get_contact_detail(self, agent_id: str) -> dict: ...

    def create_agent(self, name: str, desc: str = "",
                     prompt: str = "") -> dict: ...

    def delete_agent(self, agent_id: str) -> bool: ...
```

### 6.2 异常映射表（供 T3 Tool 层使用）

| 异常类型 | 错误码 | HTTP 类比 | Tool 层响应示例 |
|---------|--------|-----------|---------------|
| `AgentNotFoundError` | `AGENT_NOT_FOUND` | 404 | `error_response("目标 Agent 不存在", "AGENT_NOT_FOUND")` |
| `EmptyContentError` | `EMPTY_CONTENT` | 400 | `error_response("消息内容不能为空", "EMPTY_CONTENT")` |
| `DuplicateNameError` | `DUPLICATE_NAME` | 409 | `error_response("同名 Agent 已存在", "DUPLICATE_NAME")` |
| `InvalidStatusError` | `INVALID_STATUS` | 400 | `error_response("状态值不合法", "INVALID_STATUS")` |

**Tool 层错误码提取模式（推荐）：**
```python
try:
    result = service.send_message(...)
except AgentTeamError as e:
    code = type(e).__dict__.get("code", "UNKNOWN_ERROR")
    return error_response(str(e) or type(e).__name__, code)
```

### 6.3 数据模型

Agent 字典（完整）：
```python
{
    "id": str,            # uuid4
    "name": str,          # 必填，唯一
    "desc": str,          # 默认 ""
    "prompt": str,        # 默认 ""
    "status": str,        # "online" | "offline" | "busy" | "deleted"
    "created_at": str,    # ISO 8601
    "updated_at": str,    # ISO 8601
}
```

Message 字典（完整，含 sender_name）：
```python
{
    "id": str,            # uuid4
    "sender_id": str,     # 发送方 Agent ID
    "sender_name": str,   # 发送方 Agent 名称（DB 层 JOIN）
    "receiver_id": str,   # 接收方 Agent ID
    "content": str,       # 消息内容
    "is_read": int,       # 0 或 1
    "created_at": str,    # ISO 8601
}
```

---

## 7. 测试指引

### 7.1 测试执行命令

```bash
pytest tests/core/test_agent_team_service.py -v
```

### 7.2 Fake DB 实现要点

```python
class FakeAgentTeamDB:
    def __init__(self):
        self.agents: dict[str, dict] = {}
        self.messages: list[dict] = []
        self._name_index: dict[str, str] = {}  # name → id

    def get_agent(self, agent_id: str) -> dict | None:
        return self.agents.get(agent_id)

    def get_agent_by_name(self, name: str) -> dict | None:
        agent_id = self._name_index.get(name)
        return self.agents.get(agent_id) if agent_id else None

    def insert_agent(self, id, name, desc, prompt, status, created_at, updated_at) -> dict:
        agent = {"id": id, "name": name, "desc": desc, "prompt": prompt,
                 "status": status, "created_at": created_at, "updated_at": updated_at}
        self.agents[id] = agent
        self._name_index[name] = id
        return agent

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id not in self.agents:
            return False
        self.agents[agent_id]["status"] = "deleted"
        return True

    def list_agents(self, exclude_id=None, status_filter=None) -> list[dict]:
        result = [a for aid, a in self.agents.items() if aid != exclude_id]
        # 始终过滤 status='deleted'
        result = [a for a in result if a["status"] != "deleted"]
        if status_filter is not None:
            result = [a for a in result if a["status"] == status_filter]
        return result

    def insert_message(self, id, sender_id, receiver_id, content, created_at) -> dict:
        msg = {"id": id, "sender_id": sender_id, "receiver_id": receiver_id,
               "content": content, "is_read": 0, "created_at": created_at}
        self.messages.append(msg)
        return msg

    def list_messages(self, receiver_id, limit, offset, unread_only) -> tuple[list[dict], int]:
        filtered = [m for m in self.messages if m["receiver_id"] == receiver_id]
        if unread_only:
            filtered = [m for m in filtered if m["is_read"] == 0]
        total = len(filtered)
        # 按 created_at 倒序（模仿 DB 层行为）
        filtered.sort(key=lambda m: m["created_at"], reverse=True)
        page = filtered[offset:offset + limit]
        return (page, total)

    def mark_as_read(self, message_ids: list[str]) -> None:
        for msg in self.messages:
            if msg["id"] in message_ids:
                msg["is_read"] = 1

    def close(self) -> None:
        pass
```

### 7.3 测试用例数据准备模式

```python
class TestAgentTeamService:
    @pytest.fixture
    def db(self):
        """创建预填充的 fake DB。"""
        fake = FakeAgentTeamDB()
        now = datetime.now(timezone.utc).isoformat()
        # 插入 3 个 Agent 用作测试数据
        fake.insert_agent("agent-1", "Architect", "架构师", "prompt1", "online", now, now)
        fake.insert_agent("agent-2", "Coder", "编码者", "prompt2", "online", now, now)
        fake.insert_agent("agent-3", "Reviewer", "审查者", "prompt3", "offline", now, now)
        return fake

    @pytest.fixture
    def service(self, db):
        return AgentTeamService(db)

    def test_send_message_success(self, service, db):
        result = service.send_message("agent-1", "agent-2", "Hello")
        assert "id" in result
        assert "created_at" in result
        assert len(db.messages) == 1
        assert db.messages[0]["content"] == "Hello"
        assert db.messages[0]["sender_id"] == "agent-1"
```

---

## 8. 验收标准

- [ ] `src/core/agent_team.py` 文件创建，包含 4 个异常类 + `AgentTeamService` 类
- [ ] 6 个 service 方法签名与第 6.1 节完全一致
- [ ] `pytest tests/core/test_agent_team_service.py` 全部通过
- [ ] 测试覆盖 ≥ 16 个用例：6 种正常业务场景 + 参数校验 + 异常路径 + 边界条件
- [ ] `send_message` 校验 content 非空 + to_agent_id 存在性
- [ ] `delete_agent` 实现软删除（status='deleted'），历史记录可查
- [ ] `get_contacts` 永远过滤 status='deleted'，支持合法 status_filter
- [ ] `create_agent` 同名检查，name 为空抛 ValueError
- [ ] `receive_message` 自动标记返回消息为已读
- [ ] 所有方法使用 `datetime.now(timezone.utc).isoformat()` 生成 ISO 8601 时间戳
- [ ] 所有 ID 使用 `uuid.uuid4()` 生成

---

## 9. 注意事项

### 9.1 软删除语义完整性

`delete_agent` **不物理删除** Agent 记录。确保：
- `list_agents`（DB 层）在查询时始终过滤 `status != 'deleted'`
- `get_agent` 仍可返回已删除 Agent（`status='deleted'`），供消息历史展示使用
- 已删除 Agent 不再出现在 `get_contacts` 结果中

### 9.2 时间戳格式

统一使用含微秒的 ISO 8601 格式：
```python
datetime.now(timezone.utc).isoformat()
# → "2026-06-24T12:05:00.123456+00:00"
```
不要使用 `datetime.utcnow()`（已弃用），始终使用 `timezone.utc`。

### 9.3 错误设计理念

- Service 层抛 Python 异常，**不返回 JSON 错误字符串**（那是 Tool 层的职责）
- 异常携带 `.code` 类属性，Tool 层用 `type(e).__dict__.get("code", "UNKNOWN_ERROR")` 提取
- `ValueError`（name 为空）是参数校验异常，Tool 层应映射为 `INVALID_PARAMETERS` 错误码

### 9.4 DB 层依赖假设

Service 层假设 T1 交付的 `AgentTeamDB` 行为如下：
- `get_agent(agent_id)` 对不存在的 ID 返回 `None`，不抛异常
- `get_agent_by_name(name)` 对不存在的名称返回 `None`
- `list_agents(exclude_id, status_filter)` 当 `status_filter` 为 `None` 时返回所有非 deleted Agent
- `list_messages` 返回 `tuple[list[dict], int]`，消息按 `created_at DESC` 排序
- `mark_as_read(message_ids)` 空列表调用无副作用

### 9.5 与 T3 Tool 层的接口契约

Tool 层将通过以下方式使用 Service：
```python
db = AgentTeamDB(db_path)
try:
    service = AgentTeamService(db)
    result = service.send_message(sender_id=ctx_sender, ...)
    return success_response(result)
except AgentTeamError as e:
    return error_response(str(e), type(e).code)
finally:
    db.close()
```

Service 层**不持有 DB 连接生命周期**——由 Tool 层管理。

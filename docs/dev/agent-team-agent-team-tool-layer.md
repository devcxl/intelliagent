# 开发文档: T3 — Tool 层实现

**Project:** agent-team  
**Task ID:** T3  
**Slug:** agent-team-tool-layer  
**Issue:** #22  
**类型:** backend  
**Batch:** 3  
**依赖:** T2 (`agent-team-service-layer`, #21)  
**产出文件:** `src/tools/agent_team_tools.py` / `tests/tools/test_agent_team_tools.py`

---

## 1. 目标

实现 6 个 agent-team 异步 tool 函数 + `set_agent_team_context()` 上下文注入机制。Tool 层是 LLM 调用 agent-team 能力的唯一入口，通过 `src/tools/response.py` 的 `success_response` / `error_response` 构建结构化 JSON 返回给模型。

---

## 2. 前置条件

| 条件 | 说明 |
|------|------|
| T2 完成 | `src/core/agent_team.py` 可用，`AgentTeamService` 类与 4 个异常类已实现 |
| T1 完成 | `src/db/agent_team_db.py` 可用，`AgentTeamDB` 类已实现 |
| 现有约定 | `src/tools/response.py` 的 `success_response` / `error_response` 可直接 import |

---

## 3. 架构概览

```
AgentRuntime.create_engine()
  └─ set_agent_team_context(db_path, agent_id)   ← 上下文注入点
       │
       ▼
_tool_fn(...)                                     ← 6 个 async tool 函数
  ├─ _agent_team_ctx.get()                        ← 获取 (db_path, agent_id)
  ├─ AgentTeamDB(db_path)                         ← 临时创建 DB 实例
  ├─ AgentTeamService(db)                         ← 临时创建 Service 实例
  ├─ service.xxx(...)                             ← 调用业务方法
  └─ return success_response(...) / 返回 error_response(...)
```

**关键设计决策：**
- **上下文注入**：使用 `contextvars.ContextVar`（与 task_tools 的全局变量不同，但遵循同一 `set_xxx_context()` 模式）
- **连接生命周期**：每次 tool 调用内部创建/销毁 DB 与 Service 实例，不维护长连接
- **错误处理**：上下文缺失或不合法参数均返回结构化 JSON 错误（不抛异常）

---

## 4. 实现步骤

### 4.1 新建 `src/tools/agent_team_tools.py`

#### 4.1.1 上下文注入

```python
# src/tools/agent_team_tools.py

"""Agent Team 内置工具 — 6 个异步 tool 函数 + 上下文注入。

上下文注入对标 task_tools.set_task_context() 模式，但使用 ContextVar
保证 asyncio 安全性和并发隔离。
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

from src.core.agent_team import (
    AgentTeamService,
    AgentNotFoundError,
    EmptyContentError,
    DuplicateNameError,
    InvalidStatusError,
)
from src.db.agent_team_db import AgentTeamDB
from src.tools.response import error_response, success_response

logger = logging.getLogger(__name__)

# ── 上下文 ──────────────────────────────────────────────────────────────
# ContextVar 存储 (db_path, agent_id)，None 表示未初始化
_agent_team_ctx: ContextVar[tuple[str, str] | None] = ContextVar(
    "agent_team_ctx", default=None
)


def set_agent_team_context(db_path: str | None, agent_id: str | None) -> None:
    """设置或清除 Agent Team 上下文。

    由 AgentRuntime.create_engine() 在创建 Engine 时调用。

    Args:
        db_path: SQLite 数据库文件路径，None 时清除上下文
        agent_id: 当前 Agent ID，None 时清除上下文
    """
    if db_path is not None and agent_id is not None:
        _agent_team_ctx.set((db_path, agent_id))
    else:
        _agent_team_ctx.set(None)
```

#### 4.1.2 内部辅助函数

```python
def _get_service() -> tuple[AgentTeamService, str]:
    """获取 Service 实例和当前 Agent ID。

    Returns:
        (AgentTeamService 实例, 当前 agent_id)

    Raises:
        LookupError: 上下文未初始化
    """
    ctx = _agent_team_ctx.get()
    if ctx is None:
        raise LookupError("Agent Team 上下文未初始化")
    db_path, agent_id = ctx
    db = AgentTeamDB(db_path)
    db.init_db()
    return AgentTeamService(db), agent_id


def _context_error() -> str:
    """返回上下文缺失的标准错误响应。"""
    return error_response("Agent Team 上下文未初始化", "CONTEXT_NOT_INITIALIZED")
```

#### 4.1.3 异常 → 错误码映射

```python
# 异常 → (错误描述模板, 错误码) 映射表
_EXCEPTION_MAP: dict[type[Exception], tuple[str, str]] = {
    AgentNotFoundError: ("Agent 不存在: {}", "AGENT_NOT_FOUND"),
    EmptyContentError: ("消息内容不能为空", "EMPTY_CONTENT"),
    DuplicateNameError: ("Agent 名称已存在: {}", "DUPLICATE_NAME"),
    InvalidStatusError: ("无效的状态值: {}", "INVALID_STATUS"),
}
```

#### 4.1.4 6 个 Tool 函数

**send_message**

```python
async def send_message(to_agent_id: str, content: str) -> str:
    """向指定 Agent 发送消息。

    发送方身份由上下文注入，不可通过参数伪造。

    Args:
        to_agent_id: 目标 Agent ID（必填）
        content: 消息内容（必填）

    Returns:
        JSON: {"status":"ok","message_id":"<uuid>","created_at":"<iso8601>"}
        错误: {"status":"error","error":"...","code":"AGENT_NOT_FOUND|EMPTY_CONTENT|CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, agent_id = _get_service()
    except LookupError:
        return _context_error()

    try:
        result = service.send_message(
            sender_id=agent_id, to_agent_id=to_agent_id, content=content
        )
        return success_response({
            "message_id": result["id"],
            "created_at": result["created_at"],
        })
    except (AgentNotFoundError, EmptyContentError) as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)
```

**receive_message**

```python
async def receive_message(
    limit: int = 20, offset: int = 0, unread_only: bool = False
) -> str:
    """接收当前 Agent 的收件箱消息。

    返回的消息自动标记为已读。

    Args:
        limit: 返回条数上限（默认 20）
        offset: 偏移量（默认 0）
        unread_only: 仅返回未读消息（默认 False）

    Returns:
        JSON: {"status":"ok","messages":[...],"total":42}
        错误: {"status":"error","error":"...","code":"CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, agent_id = _get_service()
    except LookupError:
        return _context_error()

    messages, total = service.receive_message(
        receiver_id=agent_id, limit=limit, offset=offset, unread_only=unread_only
    )
    return success_response({"messages": messages, "total": total})
```

**get_contacts**

```python
async def get_contacts(status: str | None = None) -> str:
    """查询通讯录，返回除当前 Agent 外的所有 Agent。

    Args:
        status: 按状态过滤（online / offline / busy），不传则返回全部

    Returns:
        JSON: {"status":"ok","contacts":[...]}
        错误: {"status":"error","error":"...","code":"CONTEXT_NOT_INITIALIZED|INVALID_STATUS"}
    """
    try:
        service, agent_id = _get_service()
    except LookupError:
        return _context_error()

    try:
        contacts = service.get_contacts(
            current_agent_id=agent_id, status_filter=status
        )
        return success_response({"contacts": contacts})
    except InvalidStatusError as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)
```

**get_contact_detail**

```python
async def get_contact_detail(agent_id: str) -> str:
    """获取指定 Agent 的详细信息。

    Args:
        agent_id: 目标 Agent ID（必填）

    Returns:
        JSON: {"status":"ok","agent":{...}}
        错误: {"status":"error","error":"...","code":"AGENT_NOT_FOUND|CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        agent = service.get_contact_detail(agent_id=agent_id)
        return success_response({"agent": agent})
    except AgentNotFoundError as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)
```

**create_agent**

```python
async def create_agent(
    name: str, desc: str = "", prompt: str = ""
) -> str:
    """创建新 Agent。

    Agent ID 由系统自动生成（UUID），不在参数中暴露。

    Args:
        name: Agent 名称（必填，不可重名）
        desc: Agent 描述
        prompt: Agent 系统提示词

    Returns:
        JSON: {"status":"ok","agent":{...}}
        错误: {"status":"error","error":"...","code":"DUPLICATE_NAME|CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        agent = service.create_agent(name=name, desc=desc, prompt=prompt)
        return success_response({"agent": agent})
    except DuplicateNameError as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)
```

**delete_agent**

```python
async def delete_agent(agent_id: str) -> str:
    """删除指定 Agent（软删除：status = 'deleted'）。

    消息历史保留，不级联删除。

    Args:
        agent_id: 目标 Agent ID（必填）

    Returns:
        JSON: {"status":"ok","deleted":true}
        错误: {"status":"error","error":"...","code":"AGENT_NOT_FOUND|CONTEXT_NOT_INITIALIZED"}
    """
    try:
        service, _ = _get_service()
    except LookupError:
        return _context_error()

    try:
        deleted = service.delete_agent(agent_id=agent_id)
        return success_response({"deleted": deleted})
    except AgentNotFoundError as e:
        desc_template, code = _EXCEPTION_MAP[type(e)]
        return error_response(desc_template.format(str(e)), code)
```

#### 4.1.5 模块公开接口

```python
__all__ = [
    "set_agent_team_context",
    "send_message",
    "receive_message",
    "get_contacts",
    "get_contact_detail",
    "create_agent",
    "delete_agent",
]
```

### 4.2 新建 `tests/tools/test_agent_team_tools.py`

#### 4.2.1 测试策略

| 类别 | 用例数 | 说明 |
|------|--------|------|
| 上下文缺失 | 6 | 每个 tool 在无上下文时返回 `CONTEXT_NOT_INITIALIZED` |
| 正常路径 | 6 | 每个 tool 的完整 JSON 输入 → 输出验证 |
| 参数校验 / 异常路径 | 4+ | 空消息、不存在的 Agent、重名、无效状态 |
| 端到端流程 | 1~2 | send → receive 完整往返 |

#### 4.2.2 Fixture 设计

```python
# tests/tools/test_agent_team_tools.py

"""Agent Team Tool 层单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.db.agent_team_db import AgentTeamDB
from src.tools.agent_team_tools import (
    set_agent_team_context,
    send_message,
    receive_message,
    get_contacts,
    get_contact_detail,
    create_agent,
    delete_agent,
)


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """创建临时 SQLite 数据库文件路径。"""
    return str(tmp_path / "test_agent_team.db")


@pytest.fixture
def initialized_db(db_path: str) -> str:
    """初始化数据库结构并返回路径。"""
    db = AgentTeamDB(db_path)
    db.init_db()
    # 预置一个接收方 Agent 用于发送消息测试
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    db.insert_agent(
        id=str(uuid.uuid4()),
        name="Receiver",
        desc="接收方",
        prompt="",
        status="online",
        created_at=now,
        updated_at=now,
    )
    return db_path


@pytest.fixture
def agent_ctx(db_path: str) -> str:
    """设置上下文并返回当前 Agent ID。"""
    agent_id = "agent-tester-001"
    set_agent_team_context(db_path, agent_id)
    yield agent_id
    set_agent_team_context(None, None)


@pytest.fixture
def populated_ctx(initialized_db: str):
    """准备好的上下文 + 已存在的接收方。"""
    agent_id = "agent-tester-001"
    set_agent_team_context(initialized_db, agent_id)
    yield agent_id
    set_agent_team_context(None, None)
```

#### 4.2.3 测试用例

```python
class TestContextNotInitialized:
    """上下文缺失错误覆盖 — 每个 tool 返回 CONTEXT_NOT_INITIALIZED。"""

    @pytest.mark.asyncio
    async def test_send_message_no_context(self):
        """send_message: 上下文未注入。"""
        result = await send_message(to_agent_id="any", content="hello")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_receive_message_no_context(self):
        """receive_message: 上下文未注入。"""
        result = await receive_message()
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_get_contacts_no_context(self):
        """get_contacts: 上下文未注入。"""
        result = await get_contacts()
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_get_contact_detail_no_context(self):
        """get_contact_detail: 上下文未注入。"""
        result = await get_contact_detail(agent_id="any")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_create_agent_no_context(self):
        """create_agent: 上下文未注入。"""
        result = await create_agent(name="TestAgent")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "CONTEXT_NOT_INITIALIZED"

    @pytest.mark.asyncio
    async def test_delete_agent_no_context(self):
        """delete_agent: 上下文未注入。"""
        result = await delete_agent(agent_id="any")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "CONTEXT_NOT_INITIALIZED"


class TestSendMessageTool:
    """send_message tool 测试。"""

    @pytest.mark.asyncio
    async def test_send_success(self, populated_ctx):
        """正常发送消息 → 返回 message_id + created_at。"""
        # 获取预置的接收方 ID
        db = AgentTeamDB(
            # 从上下文中还原 db_path（populated_ctx 通过 monkeypatch 不可直接取）
            # 实际通过 fixture 配合：在 populated_ctx 中获取目标 Agent
        )
        ...
        result = await send_message(to_agent_id="...", content="hello team")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "message_id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_send_empty_content(self, populated_ctx):
        """空消息内容 → EMPTY_CONTENT。"""
        result = await send_message(to_agent_id="any", content="")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "EMPTY_CONTENT"

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_agent(self, populated_ctx):
        """发送给不存在的 Agent → AGENT_NOT_FOUND。"""
        result = await send_message(
            to_agent_id="nonexistent-agent", content="hello"
        )
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "AGENT_NOT_FOUND"


class TestReceiveMessageTool:
    """receive_message tool 测试。"""

    @pytest.mark.asyncio
    async def test_receive_empty_inbox(self, populated_ctx):
        """空收件箱 → 返回空列表。"""
        result = await receive_message()
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["messages"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_receive_pagination(self, populated_ctx):
        """分页查询：先发多条消息再按 limit/offset 接收。"""
        ...

    @pytest.mark.asyncio
    async def test_receive_mark_as_read(self, populated_ctx):
        """接收消息后自动标记为已读。"""
        ...


class TestGetContactsTool:
    """get_contacts tool 测试。"""

    @pytest.mark.asyncio
    async def test_get_contacts_excludes_current(self, populated_ctx):
        """通讯录排除当前 Agent。"""
        ...

    @pytest.mark.asyncio
    async def test_get_contacts_filter_by_status(self, populated_ctx):
        """按状态过滤。"""
        ...

    @pytest.mark.asyncio
    async def test_get_contacts_invalid_status(self, populated_ctx):
        """非法状态值 → INVALID_STATUS。"""
        result = await get_contacts(status="invalid_status_value")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "INVALID_STATUS"


class TestGetContactDetailTool:
    """get_contact_detail tool 测试。"""

    @pytest.mark.asyncio
    async def test_get_detail_success(self, populated_ctx):
        """获取已存在 Agent 的详情。"""
        ...

    @pytest.mark.asyncio
    async def test_get_detail_not_found(self, populated_ctx):
        """获取不存在的 Agent → AGENT_NOT_FOUND。"""
        result = await get_contact_detail(agent_id="nonexistent")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "AGENT_NOT_FOUND"


class TestCreateAgentTool:
    """create_agent tool 测试。"""

    @pytest.mark.asyncio
    async def test_create_success(self, agent_ctx):
        """正常创建 Agent → 返回完整 Agent 字典。"""
        result = await create_agent(name="NewAgent", desc="描述", prompt="提示")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["agent"]["name"] == "NewAgent"
        assert "id" in data["agent"]
        assert data["agent"]["status"] == "offline"

    @pytest.mark.asyncio
    async def test_create_duplicate_name(self, agent_ctx):
        """重名 → DUPLICATE_NAME。"""
        await create_agent(name="UniqueAgent")
        result = await create_agent(name="UniqueAgent")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "DUPLICATE_NAME"

    @pytest.mark.asyncio
    async def test_create_default_values(self, agent_ctx):
        """默认 desc 和 prompt 为空字符串。"""
        result = await create_agent(name="MinimalAgent")
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["agent"]["desc"] == ""
        assert data["agent"]["prompt"] == ""


class TestDeleteAgentTool:
    """delete_agent tool 测试。"""

    @pytest.mark.asyncio
    async def test_delete_success(self, agent_ctx):
        """正常删除 → deleted: true，软删除后不再出现在通讯录。"""
        create_resp = json.loads(await create_agent(name="ToDelete"))
        target_id = create_resp["agent"]["id"]

        result = await delete_agent(agent_id=target_id)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert data["deleted"] is True

        # 验证已不出现在通讯录中
        contacts_resp = json.loads(await get_contacts())
        contact_ids = [c["id"] for c in contacts_resp["contacts"]]
        assert target_id not in contact_ids

    @pytest.mark.asyncio
    async def test_delete_not_found(self, agent_ctx):
        """删除不存在的 Agent → AGENT_NOT_FOUND。"""
        result = await delete_agent(agent_id="nonexistent")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == "AGENT_NOT_FOUND"


class TestEndToEndFlow:
    """端到端流程测试。"""

    @pytest.mark.asyncio
    async def test_send_and_receive_roundtrip(self, populated_ctx):
        """发送消息 → 接收消息 → 验证消息已读完整链路。"""
        ...

    @pytest.mark.asyncio
    async def test_multi_agent_communication(self, db_path):
        """多 Agent 间消息收发。"""
        ...
```

---

## 5. 接口 / 契约

### 5.1 上下文注入

```python
def set_agent_team_context(db_path: str | None, agent_id: str | None) -> None:
    """设置或清除 Agent Team 上下文。

    用法:
        # 设置上下文（AgentRuntime.create_engine 内调用）
        set_agent_team_context("/path/to/intelliagent.db", "agent-001")

        # 清除上下文（测试 teardown / 引擎销毁）
        set_agent_team_context(None, None)
    """
```

### 5.2 6 个 Tool 函数签名

| Tool | 函数签名 | 必需参数 | 可选参数（含默认值） |
|------|---------|---------|---------------------|
| `send_message` | `async def send_message(to_agent_id: str, content: str) -> str` | `to_agent_id`, `content` | — |
| `receive_message` | `async def receive_message(limit: int = 20, offset: int = 0, unread_only: bool = False) -> str` | — | `limit`, `offset`, `unread_only` |
| `get_contacts` | `async def get_contacts(status: str \| None = None) -> str` | — | `status` |
| `get_contact_detail` | `async def get_contact_detail(agent_id: str) -> str` | `agent_id` | — |
| `create_agent` | `async def create_agent(name: str, desc: str = "", prompt: str = "") -> str` | `name` | `desc`, `prompt` |
| `delete_agent` | `async def delete_agent(agent_id: str) -> str` | `agent_id` | — |

### 5.3 成功响应格式

| Tool | 成功 JSON |
|------|----------|
| `send_message` | `{"status":"ok","message_id":"<uuid>","created_at":"<iso8601>"}` |
| `receive_message` | `{"status":"ok","messages":[...],"total":<int>}` |
| `get_contacts` | `{"status":"ok","contacts":[...]}` |
| `get_contact_detail` | `{"status":"ok","agent":{...}}` |
| `create_agent` | `{"status":"ok","agent":{...}}` |
| `delete_agent` | `{"status":"ok","deleted":true}` |

### 5.4 错误码全集

| 错误码 | 触发条件 | 涉及 Tool |
|--------|---------|----------|
| `CONTEXT_NOT_INITIALIZED` | `_agent_team_ctx.get()` 返回 None | 全部 6 个 |
| `AGENT_NOT_FOUND` | 目标 Agent 不存在 | `send_message`, `get_contact_detail`, `delete_agent` |
| `EMPTY_CONTENT` | `send_message` 的 content 为空 | `send_message` |
| `DUPLICATE_NAME` | 创建同名 Agent | `create_agent` |
| `INVALID_STATUS` | `get_contacts` 的 status 值不合法 | `get_contacts` |

---

## 6. 测试指引

### 6.1 运行命令

```bash
# 仅跑 T3 的测试
pytest tests/tools/test_agent_team_tools.py -v

# 带覆盖率
pytest tests/tools/test_agent_team_tools.py -v --cov=src.tools.agent_team_tools --cov-report=term-missing
```

### 6.2 测试数据准备

```python
# 创建临时数据库文件（使用 pytest tmp_path fixture）
db_path = str(tmp_path / "test_agent_team.db")

# 初始化数据库结构
db = AgentTeamDB(db_path)
db.init_db()

# 预置测试 Agent（可选）
import uuid
from datetime import datetime, timezone

now = datetime.now(timezone.utc).isoformat()
receiver_id = str(uuid.uuid4())
db.insert_agent(
    id=receiver_id, name="TestReceiver", desc="", prompt="",
    status="online", created_at=now, updated_at=now,
)

# 注入上下文
set_agent_team_context(db_path, "agent-tester-001")

# 执行 tool 调用...
await send_message(to_agent_id=receiver_id, content="hello")

# 清理上下文
set_agent_team_context(None, None)
```

### 6.3 必须覆盖的测试场景

| # | 场景 | 验证点 |
|---|------|--------|
| 1 | 上下文未注入，调用每个 tool | 返回 `{"status":"error","code":"CONTEXT_NOT_INITIALIZED"}` |
| 2 | `send_message` 正常发送 | 返回 `message_id` + `created_at`，消息可被接收方查询到 |
| 3 | `send_message` 空内容 | 返回 `EMPTY_CONTENT` |
| 4 | `send_message` 目标不存在 | 返回 `AGENT_NOT_FOUND` |
| 5 | `receive_message` 空收件箱 | 返回空 `messages` 列表 + `total: 0` |
| 6 | `receive_message` 分页（limit/offset） | 验证分页数据正确性 |
| 7 | `receive_message` 自动标记已读 | 接收后再次查询 is_read=1 |
| 8 | `get_contacts` 排除当前 Agent | 返回列表不含当前 agent_id |
| 9 | `get_contacts` 按状态过滤 | 过滤逻辑正确 |
| 10 | `get_contacts` 非法状态 | 返回 `INVALID_STATUS` |
| 11 | `get_contact_detail` 存在 | 返回完整 Agent 字典 |
| 12 | `get_contact_detail` 不存在 | 返回 `AGENT_NOT_FOUND` |
| 13 | `create_agent` 正常创建 | 返回含 `id`、`name` 等字段的 Agent 字典 |
| 14 | `create_agent` 重名 | 返回 `DUPLICATE_NAME` |
| 15 | `create_agent` 默认值验证 | `desc` 和 `prompt` 为空字符串时正确 |
| 16 | `delete_agent` 存在 | 返回 `deleted: true`，通讯录中已移除 |
| 17 | `delete_agent` 不存在 | 返回 `AGENT_NOT_FOUND` |
| 18 | 端到端：send → receive 完整链路 | 消息收发正确，已读状态正确 |

---

## 7. 验收标准

- [ ] `pytest tests/tools/test_agent_team_tools.py` 全部通过（0 失败）
- [ ] 6 个 tool 的上下文缺失路径全部覆盖（每个 tool 返回 `CONTEXT_NOT_INITIALIZED`）
- [ ] 异常路径覆盖：`AGENT_NOT_FOUND`、`EMPTY_CONTENT`、`DUPLICATE_NAME`、`INVALID_STATUS`
- [ ] 每个 tool 的正常路径含 JSON 输出字段完整性断言
- [ ] 端到端 send → receive 往返测试通过
- [ ] 模块文件 `src/tools/agent_team_tools.py` 存在且 `__all__` 导出 7 个符号

---

## 8. 注意事项

1. **上下文缺失不抛异常** — 返回结构化 `error_response("...", "CONTEXT_NOT_INITIALIZED")`，让 LLM 可以解读错误并提示用户初始化 Agent Team
2. **对标 task_tools 模式** — 上下文注入函数签名 `set_agent_team_context(...)` 与 `set_task_context(...)` 风格一致，但内部使用 `ContextVar` 替代全局变量以保证 asyncio 安全
3. **DB 连接生命周期** — 每次 tool 调用临时创建 `AgentTeamDB` / `AgentTeamService`，用完即关，不维护连接池。与 `task_tools` 的 session factory 模式不同
4. **异常映射集中管理** — `_EXCEPTION_MAP` 字典统一维护异常类到错误码的映射，新增异常类型时只需添加一行
5. **Service 层是同步 API** — `AgentTeamService` 所有方法返回 dict 或 raise 异常，tool 函数标记为 `async def` 以兼容 `ToolRegistry.call_tool()` 的 `await` 调用，但不涉及 `await` Service 方法
6. **sender_id 不可伪造** — 当前 Agent 身份从 `_agent_team_ctx` 获取，`send_message` 的 tool 参数不包含 sender_id，防止 Agent 冒充他人
7. **T4（Tool 注册）依赖本模块** — `__all__` 导出的 6 个 tool 函数名即为 T4 中 `registry.py` import 的符号名，名称需严格对应

# 审查报告: PR #25

## 审查概要

- **PR 标题**: T1: DB 层实现 (closes #20)
- **变更文件数**: 3（全部为新建文件）
- **变更范围**: `src/db/agent_team_db.py` (202 行)、`tests/db/test_agent_team_db.py` (452 行)、`tests/db/__init__.py` (空文件)
- **风险等级**: 低
- **测试结果**: 26/26 通过，ruff 检查通过
- **越界修改**: 无

## 变更概述

实现 `AgentTeamDB` 类 — 纯标准库 `sqlite3` 的 Agent + Message 持久化层：

- `__init__(db_path)` → 打开连接，启用 WAL 模式 + 外键约束，自动创建目录
- `init_db()` → 幂等建表（`agents`、`agent_messages`）+ 2 个索引
- Agent CRUD: `insert_agent`、`get_agent`、`get_agent_by_name`、`list_agents`（支持 exclude_id / status_filter）、`delete_agent`（软删除）
- Message CRUD: `insert_message`、`list_messages`（JOIN sender_name + 分页）、`mark_as_read`（批量）
- 26 个测试用例覆盖：建表幂等性、Agent CRUD 全路径、Message CRUD 全路径、索引验证、软删除语义、边界条件

---

## 问题列表

### 安全性检查（CRITICAL）

✅ **无硬编码密钥/密码/token**
✅ **SQL 注入防护充分** — 所有查询使用参数化绑定（`?` 占位符），`list_messages` 计数查询的 f-string 仅包裹硬编码 SQL 常量字符串
✅ **无路径遍历风险** — `db_path` 来自配置系统，非用户可控输入
✅ **无认证/授权漏洞** — DB 层不涉及权限

### HIGH

无发现。

### MEDIUM

**[MEDIUM-1] 缺少通用 `update_agent` 方法**
- 文件: `src/db/agent_team_db.py`
- 问题: DB 层提供了完整的 Agent CR（insert/get/list）和 D（delete_agent 软删除），但缺少通用的 Update 方法。`delete_agent` 仅能设置 `status='deleted'`，无法将 Agent 状态更改为其他合法值（`online`/`offline`/`busy`）或更新 `desc`/`prompt` 字段。T2 Service 层可能需要此能力。
- 修复建议: 开发文档（Issue #20 评论）未明确要求此方法，建议在 T2 启动前补充以下方法，或在开发文档中明确由 Service 层直接执行 UPDATE：

```python
def update_agent(
    self,
    agent_id: str,
    *,
    name: str | None = None,
    desc: str | None = None,
    prompt: str | None = None,
    status: str | None = None,
) -> dict | None:
    """更新 Agent 字段，返回更新后的完整 dict。不存在的字段保持原值。"""
    now = datetime.now(timezone.utc).isoformat()
    # 动态构建 SET 子句...
    # 返回 self.get_agent(agent_id)
```

**[MEDIUM-2] `list_agents` 组合过滤路径缺少测试覆盖**
- 文件: `tests/db/test_agent_team_db.py`
- 问题: `list_agents(exclude_id=..., status_filter=...)` 支持两个参数同时使用，但无测试覆盖此组合场景。测试仅覆盖了单独使用 `exclude_id` 和单独使用 `status_filter` 的情况。
- 修复建议: 新增测试用例验证同时传入两个参数时的行为：

```python
def test_list_agents_exclude_and_status_filter(self, db):
    # 插入多个 Agent，传入 exclude_id + status_filter
    result = db.list_agents(exclude_id="a1", status_filter="online")
    assert all(r["id"] != "a1" for r in result)
    assert all(r["status"] == "online" for r in result)
```

**[MEDIUM-3] `test_wal_mode_enabled` 参数类型标注不当**
- 文件: `tests/db/test_agent_team_db.py:444`
- 问题: 测试函数参数 `tmp_path: object` 使用了过于宽泛的类型标注。`tmp_path` 实际是 `pathlib.Path` 类型。更严重的是，`object` 类型上没有 `.parent` 属性，mypy 严格模式会报错。
- 修复建议:

```python
# 方案 A（推荐）: 移除类型标注，让 pytest 推断
def test_wal_mode_enabled(self, tmp_path):

# 方案 B: 使用正确类型
from pathlib import Path
def test_wal_mode_enabled(self, tmp_path: Path):
```

**[MEDIUM-4] `insert_message` 返回值的构造方式与 `insert_agent` 不一致**
- 文件: `src/db/agent_team_db.py:141-148`
- 问题: `insert_agent` 通过 `self.get_agent(id)` 从 DB 回读数据，确保返回值与 DB 实际状态一致。而 `insert_message` 手工构造字典返回，如果将来添加触发器、默认值变更或 DB 写入静默失败，返回值可能与实际数据不一致。
- 修复建议: 统一为 DB 回读方式，或至少在方法文档中说明此差异的意图：

```python
def insert_message(self, ...) -> dict:
    self._conn.execute(...)
    self._conn.commit()
    # 统一从 DB 回读，保证返回值与持久化数据一致
    row = self._conn.execute(
        "SELECT id, sender_id, receiver_id, content, is_read, created_at "
        "FROM agent_messages WHERE id = ?", (id,)
    ).fetchone()
    return dict(row)
```

### LOW

- `desc` 列名是 SQL 保留关键字（`agent-team.md` §4.2 DDL 指定此命名，实现遵循规范，无实际冲突）
- `list_agents` 使用 `WHERE 1=1` 动态 SQL 构建模式（常见惯用法，可接受）

---

## 验收标准对照

对照 Issue #20 开发文档（评论 ID: IC_kwDOQXT3_s8AAAABHR_tYQ）的验收标准逐条检查：

| # | 验收标准 | 状态 | 说明 |
|---|---------|------|------|
| 1 | `pytest tests/db/test_agent_team_db.py` 全部通过 | ✅ | 26/26 通过（实测 0.23s） |
| 2 | 覆盖：建表幂等性 | ✅ | `test_init_is_idempotent` 验证 |
| 3 | 覆盖：Agent CRUD 全路径 | ✅ | 9 个测试覆盖 insert/get/get_by_name/list/delete |
| 4 | 覆盖：Message CRUD 全路径 | ✅ | 7 个测试覆盖 insert/list/pagination/mark_as_read |
| 5 | 覆盖：索引有效性 | ✅ | `test_indexes_exist` 验证两个索引存在 |
| 6 | 覆盖：软删除语义 | ✅ | `test_delete_agent_success` + `test_soft_deleted_agent_still_queryable` |
| 7 | 覆盖：边界条件 | ✅ | 6 个边界用例: 不存在查询、空列表标记、重复ID/name、无效status、WAL验证、无外键验证 |
| 8 | 不使用 ORM/SQLAlchemy | ✅ | 纯标准库 `sqlite3`，零第三方依赖 |
| 9 | `agent_messages` 表无外键约束 | ✅ | `test_no_foreign_key_on_messages` 直接验证 DDL 无 `FOREIGN KEY` + `REFERENCES` |
| 10 | WAL 模式生效 | ✅ | `test_wal_mode_enabled` 验证 `PRAGMA journal_mode` 返回 `wal` |
| 11 | 代码通过 ruff 检查 | ✅ | `ruff check` + `ruff format` 均通过 |
| 12 | DDL 与开发文档一致 | ✅ | 开发文档标注"⚠️ 差异：技术方案中 DDL 写有 REFERENCES agents(id)，但任务图 S1 要求不使用外键约束。本处 DDL 为实现权威版本" — 实现与此要求完全一致 |
| 13 | `agents.name` UNIQUE 约束 | ✅ | DDL 包含 `UNIQUE`，测试验证同名插入抛出 `IntegrityError` |
| 14 | `agents.status` 含 `deleted` | ✅ | CHECK 约束包含 `'deleted'`，支持软删除 |
| 15 | 变更范围无越界 | ✅ | 仅 3 个新建文件，无现有文件修改 |
| 16 | 无回归风险 | ✅ | 纯新增模块，与现有 SQLAlchemy `src/db/models.py` 完全独立 |

---

## 测试建议

当前 26 个测试覆盖已较为充分，建议在后续任务中补充：

1. **性能测试**（T3/T5 阶段）: 验证消息写入 < 10ms、列表查询 < 50ms 的性能指标（`agent-team.md` §10.1）
2. **并发测试**: 多线程/多协程同时读写 WAL 模式下的行为验证
3. **大数据量分页测试**: `list_messages` 在万级消息量下的分页性能和总数查询效率
4. **`list_agents` 组合过滤**（见 MEDIUM-2）

---

## 审查结论

✅ **通过（Approve）**

无 Critical/High 级别问题。4 个 MEDIUM 问题中，MEDIUM-1（缺少 `update_agent`）是设计层面需要在 T2 前明确的补充项，其余 3 个为测试覆盖和代码一致性改进建议，均不阻塞合并。

代码质量评价：
- **安全性**: ✅ 参数化查询防护充分
- **正确性**: ✅ 26 个测试全通过，开发文档验收标准全部满足
- **可维护性**: ✅ 代码结构清晰、命名一致、docstring 完备
- **架构符合度**: ✅ 严格遵循三层分离设计（DB/Service/Tool），纯 sqlite3 零 ORM，DDL 完全匹配开发文档

建议 T2 开发启动时优先确认 MEDIUM-1（`update_agent` 需求），避免 Service 层实现受阻。

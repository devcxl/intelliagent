## 审查报告 — PR #26：T2: Service 层实现

### 变更概述
- **修改文件数：** 3（2 个新建源文件 + 1 个包标记文件）
- **新增：** `src/core/agent_team.py`（130 行）、`tests/core/test_agent_team_service.py`（316 行）、`tests/core/__init__.py`
- **风险等级：** 低

### 验收标准对照

| 验收标准 | 状态 |
|---------|------|
| `pytest tests/core/test_agent_team_service.py` 全部通过 | ✅ 22/22 passed |
| 6 种业务场景全路径覆盖 | ✅ send_message / receive_message / get_contacts / get_contact_detail / create_agent / delete_agent |
| 参数校验覆盖 | ✅ 空内容、纯空白、不存在的 Agent、非法 status、空名称、同名冲突 |
| 异常路径覆盖 | ✅ EmptyContentError / AgentNotFoundError / InvalidStatusError / DuplicateNameError / ValueError |
| `create_agent` 空名抛 `ValueError` | ✅ 含 whitespace 场景 |
| 现有测试无回归 | ✅ 全部通过 |

### 发现问题

#### [MEDIUM] 1. `_VALID_STATUSES` 死代码
- **文件：** `src/core/agent_team.py:37`
- **问题：** 定义了 `_VALID_STATUSES = frozenset({"online", "offline", "busy", "deleted"})`，但整个模块中没有任何地方引用它。只有 `_CONTACT_STATUSES` 被 `get_contacts` 使用。
- **修复建议：** 删除第 37 行，或在未来 Tool 层需要校验 status 时使用。目前属于 YAGNI 违规。

```python
# 删除：
# _VALID_STATUSES = frozenset({"online", "offline", "busy", "deleted"})
```

#### [MEDIUM] 2. `receive_message` 缺少 receiver 存在性校验
- **文件：** `src/core/agent_team.py:71-82`
- **问题：** `send_message` 校验了目标 Agent 是否存在（抛 `AgentNotFoundError`），但 `receive_message` 没有校验 `receiver_id` 对应的 Agent 是否存在。如果传入不存在的 receiver_id，DB 层静默返回空列表，不会报错——这与 `send_message` 的不对称可能导致难以排查的问题。
- **待讨论：** 设计文档中 `receive_message` 的错误只列出了 `CONTEXT_NOT_INITIALIZED`（Tool 层），Service 层是否需要校验取决于设计意图。如果 Tool 层保证 receiver_id 来自 ContextVar（始终有效），则无需修改。否则建议对齐 `send_message` 的校验行为。

#### [LOW] 3. 建议补充 sender 被删除后的消息查询测试
- **文件：** `tests/core/test_agent_team_service.py`
- **问题：** 当 sender Agent 被软删除后，`receive_message` 返回的消息中 `sender_name` 仍然有效（因为软删除保留了 Agent 记录）。这是一个正确的行为，但有测试覆盖会更清晰。建议补充一个测试用例：sender 软删除后 `receive_message` 仍能获取 `sender_name`。
- **修复建议：**

```python
def test_receive_message_sender_deleted(self, service, db):
    """sender 被软删除后，消息的 sender_name 仍然有效。"""
    db.delete_agent("agent-1")
    db.insert_message("msg-1", "agent-1", "agent-2", "Hello", "2026-06-24T12:00:00")
    messages, _ = service.receive_message("agent-2")
    assert messages[0]["sender_name"] == "Architect"
```

### 测试覆盖分析

| 模块 | 测试数 | 覆盖场景 |
|------|--------|---------|
| `send_message` | 4 | 正常发送 / 空内容 / 纯空白 / 目标不存在 |
| `receive_message` | 5 | 正常收消息 / 自动标已读 / 分页 / unread_only / 含 sender_name |
| `get_contacts` | 5 | 全部查询 / 排除 deleted / 状态过滤 / 非法状态 / deleted 状态过滤 |
| `get_contact_detail` | 2 | 正常查询 / Agent 不存在 |
| `create_agent` | 4 | 正常创建 / 空名称 / 纯空白名称 / 同名冲突 |
| `delete_agent` | 3 | 正常软删除 / Agent 不存在 / 记录保留 |

**盲区：**
- `receive_message` 当 receiver 不存在时的行为（无测试覆盖）
- sender 被删除后消息查询的 `sender_name` 行为（无显式测试）
- `limit`/`offset` 的边界值（如 negative、0 值）——不过当前业务场景合理，标记 Low

### 代码质量

| 维度 | 评价 |
|------|------|
| 命名 | ✅ 清晰、语义化（`AgentNotFoundError`、`EmptyContentError` 等） |
| 函数体长度 | ✅ 全部 ≤ 20 行，单函数最长 18 行 |
| 文件大小 | ✅ 源文件 130 行，测试文件 316 行 |
| 嵌套层级 | ✅ ≤ 2 层 |
| 错误处理 | ✅ 异常类有 `code` 属性，方便 Tool 层映射到 JSON 错误码 |
| 设计一致性 | ✅ 与设计文档 `docs/design/agent-team.md` 接口签名完全一致 |
| 依赖方向 | ✅ Service → DB，单向依赖，无反向引用 |
| Fake DB 模拟度 | ✅ 完整模拟了 join、排序、分页、标记已读 |
| Lint | ✅ ruff 全部通过 |

### 审查结论

- [x] 通过 — 无 Critical 问题，Medium 问题不影响功能正确性

建议在后续提交中清理 `_VALID_STATUSES` 死代码，其余均为可选改进。

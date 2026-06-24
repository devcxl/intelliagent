# 开发文档: T4 — Tool 注册

**Project:** agent-team
**Task ID:** T4
**Slug:** agent-team-tool-registration
**Issue:** #23
**类型:** backend
**Batch:** 4
**依赖:** T3 (`agent-team-tool-layer`, #22)

---

## 1. 目标

将 `src/tools/agent_team_tools.py` 中已实现的 6 个 agent-team tool 注册到 `_default_registry`，使 LLM 可通过 function calling 调用它们。

---

## 2. 前置条件

- **T3 完成**：`src/tools/agent_team_tools.py` 中以下 6 个异步函数可用：
  - `send_message(to_agent_id, content)`
  - `receive_message(limit, offset, unread_only)`
  - `get_contacts(status)`
  - `get_contact_detail(agent_id)`
  - `create_agent(name, desc, prompt)`
  - `delete_agent(agent_id)`

- **上下文注入函数** `set_agent_team_context(db_path, agent_id)` 在 `agent_team_tools.py` 中已定义

---

## 3. 实现步骤

### 3.1 修改 `src/tools/registry.py`

#### 步骤 A：添加 import（在现有 task_tools import 之后）

当前 registry.py 第 11 行：

```python
from .task_tools import task_add, task_finish, task_update, task_write
```

在其后新增一行：

```python
from .agent_team_tools import (
    create_agent,
    delete_agent,
    get_contact_detail,
    get_contacts,
    receive_message,
    send_message,
)
```

#### 步骤 B：注册 6 个 tool（在 `_skill_tool` 注册块和 `__all__` 之间）

当前 registry.py 第 289 行（`_skill_tool` 注册结束）与第 292 行（`__all__`）之间插入注册代码。每个 tool 的完整注册调用如下：

##### send_message

```python
_default_registry.register(
    fn=send_message,
    name="send_message",
    description="向指定 Agent 发送消息。需要目标 Agent ID 和消息内容。发送方身份由系统上下文自动确定。",
    parameters={
        "to_agent_id": {"type": "string", "description": "目标 Agent ID", "required": True},
        "content": {"type": "string", "description": "消息内容", "required": True},
    },
)
```

##### receive_message

```python
_default_registry.register(
    fn=receive_message,
    name="receive_message",
    description="接收发送给当前 Agent 的消息（收件箱）。返回的消息会自动标记为已读。支持分页和未读过滤。",
    parameters={
        "limit": {"type": "integer", "description": "返回消息数量上限，默认 20", "required": False},
        "offset": {"type": "integer", "description": "分页偏移量，默认 0", "required": False},
        "unread_only": {"type": "boolean", "description": "仅返回未读消息，默认 false", "required": False},
    },
)
```

##### get_contacts

```python
_default_registry.register(
    fn=get_contacts,
    name="get_contacts",
    description="获取 Agent 通讯录列表。返回所有 Agent（排除当前 Agent），可按在线状态筛选。",
    parameters={
        "status": {
            "type": "string",
            "description": "按状态筛选：online / offline / busy。不传则返回全部。",
            "required": False,
        },
    },
)
```

##### get_contact_detail

```python
_default_registry.register(
    fn=get_contact_detail,
    name="get_contact_detail",
    description="获取指定 Agent 的详细信息，包括名称、描述、状态等。",
    parameters={
        "agent_id": {"type": "string", "description": "Agent ID", "required": True},
    },
)
```

##### create_agent

```python
_default_registry.register(
    fn=create_agent,
    name="create_agent",
    description="创建一个新的 Agent。Agent ID 由系统自动生成，只需提供名称、描述和系统 Prompt。",
    parameters={
        "name": {"type": "string", "description": "Agent 名称（必须唯一）", "required": True},
        "desc": {"type": "string", "description": "Agent 描述", "required": False},
        "prompt": {"type": "string", "description": "Agent 系统 Prompt", "required": False},
    },
)
```

##### delete_agent

```python
_default_registry.register(
    fn=delete_agent,
    name="delete_agent",
    description="删除指定 Agent。执行软删除（状态标记为 deleted），历史消息保留。",
    parameters={
        "agent_id": {"type": "string", "description": "要删除的 Agent ID", "required": True},
    },
)
```

---

## 4. 接口/契约

### 4.1 注册参数速查表

| Tool 名称 | 参数 | 类型 | 必填 |
|-----------|------|------|------|
| `send_message` | `to_agent_id` | string | ✅ |
| | `content` | string | ✅ |
| `receive_message` | `limit` | integer | ❌ |
| | `offset` | integer | ❌ |
| | `unread_only` | boolean | ❌ |
| `get_contacts` | `status` | string | ❌ |
| `get_contact_detail` | `agent_id` | string | ✅ |
| `create_agent` | `name` | string | ✅ |
| | `desc` | string | ❌ |
| | `prompt` | string | ❌ |
| `delete_agent` | `agent_id` | string | ✅ |

### 4.2 注册位置约束

```
src/tools/registry.py 结构（修改后）:

 1-12  从 .file_tools, .response, .shell_tool, .task_tools import ...
    ↓
 13   # 新增: from .agent_team_tools import (send_message, ...)
    ↓
 14-75 ToolDef, _to_openai_function, ToolRegistry 类定义
 76-172 _default_registry 实例化 + 现有工具注册（run_shell, read_file, ...）
273-289 _skill_tool 定义和注册
    ↓
290   # 新增: agent-team 工具注册 (6 个 register 调用)
    ↓
355   __all__ = [...]
```

**约束**：
- 注册代码在模块顶层执行（与现有模式一致）
- 插入位置严格限定在 `_skill_tool` 注册块之后、`__all__` 之前
- import 语句放在文件头部 import 区域（第 12 行之后）

---

## 5. 测试指引

### 5.1 快速验证（手动）

```bash
python -c "
from src.tools.registry import _default_registry

# 验证 tool 名称列表包含 6 个新 tool
names = _default_registry.list_tool_names()
expected = {'send_message', 'receive_message', 'get_contacts', 'get_contact_detail', 'create_agent', 'delete_agent'}
for name in expected:
    assert name in names, f'{name} not in registry'

print('所有 agent-team tool 已注册:', sorted(expected))

# 验证 OpenAI 格式无误
tools = _default_registry.get_openai_tools()
agent_team_tools = [t for t in tools if t['function']['name'] in expected]
assert len(agent_team_tools) == 6
print(f'get_openai_tools() 包含 {len(agent_team_tools)} 个 agent-team tool')
"
```

### 5.2 单元测试（建议追加到 `tests/unit/`）

参照 `tests/unit/test_skill_runtime_integration.py` 的模式，新增测试：

```python
# tests/unit/test_agent_team_registration.py

def test_agent_team_tools_registered_in_default_registry():
    """6 个 agent-team tool 已注册到 _default_registry。"""
    from src.tools.registry import _default_registry

    names = _default_registry.list_tool_names()
    expected = {"send_message", "receive_message", "get_contacts",
                "get_contact_detail", "create_agent", "delete_agent"}
    for name in expected:
        assert name in names, f"{name} 未在 _default_registry 中"


def test_send_message_has_correct_parameters():
    """send_message 参数定义正确。"""
    from src.tools.registry import _default_registry

    tool_def = _default_registry._tools.get("send_message")
    assert tool_def is not None
    assert tool_def.parameters["to_agent_id"]["required"] is True
    assert tool_def.parameters["content"]["required"] is True
    assert tool_def.parameters["to_agent_id"]["type"] == "string"
    assert tool_def.parameters["content"]["type"] == "string"


def test_receive_message_has_correct_parameters():
    """receive_message 参数定义正确。"""
    from src.tools.registry import _default_registry

    tool_def = _default_registry._tools.get("receive_message")
    assert tool_def is not None
    assert tool_def.parameters["limit"]["required"] is False
    assert tool_def.parameters["offset"]["required"] is False
    assert tool_def.parameters["unread_only"]["required"] is False
    assert tool_def.parameters["limit"]["type"] == "integer"
    assert tool_def.parameters["unread_only"]["type"] == "boolean"


def test_create_agent_has_correct_parameters():
    """create_agent 参数定义正确。"""
    from src.tools.registry import _default_registry

    tool_def = _default_registry._tools.get("create_agent")
    assert tool_def is not None
    assert tool_def.parameters["name"]["required"] is True
    assert tool_def.parameters["desc"]["required"] is False
    assert tool_def.parameters["prompt"]["required"] is False


def test_get_openai_tools_contains_agent_team_tools():
    """get_openai_tools() 返回的列表包含 6 个 agent-team tool。"""
    from src.tools.registry import _default_registry

    tools = _default_registry.get_openai_tools()
    agent_team_names = {t["function"]["name"] for t in tools} & {
        "send_message", "receive_message", "get_contacts",
        "get_contact_detail", "create_agent", "delete_agent",
    }
    assert len(agent_team_names) == 6
```

### 5.3 回归验证

```bash
# 确保现有测试不受影响
pytest tests/ -x -q
```

---

## 6. 验收标准

- [ ] `_default_registry.list_tool_names()` 包含全部 6 个 tool 名
- [ ] `_default_registry.get_openai_tools()` 返回列表包含这 6 个 tool（OpenAI function calling 格式正确）
- [ ] 每个 tool 的参数定义（type/description/required）与技术方案 4.1 节一致
- [ ] 现有测试全部通过（`pytest tests/ -x -q`）
- [ ] 注册代码插入位置正确（`_skill_tool` 之后，`__all__` 之前）

---

## 7. 注意事项

1. **模块顶层执行**：注册代码在 `import src.tools.registry` 时立即执行。`agent_team_tools` 模块被导入时会触发 `ContextVar` 定义，但不触发 DB 连接。

2. **延迟 DB 连接**：import 时不会打开 SQLite 连接。连接在 tool 实际被调用时由 `agent_team_tools.py` 内部创建并销毁，注册行为本身无副作用。

3. **import 顺序**：`agent_team_tools` 依赖 `src.core.agent_team`（Service 层）→ `src.db.agent_team_db`（DB 层）。确保 T1/T2/T3 的实现文件在 import 路径上可用。

4. **Tool 名称与函数名一致**：每个 `register()` 调用的 `name=` 参数必须与函数名以及 `agent_team_tools.py` 中的函数名完全一致，否则 `get_tool_fn()` 查找会失败。

5. **并发安全**：`ToolRegistry._tools` 是普通 `dict`，注册只在 import 时执行一次，无并发问题。

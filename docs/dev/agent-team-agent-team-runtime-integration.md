# 开发文档: T5 — 运行时集成

**Project:** agent-team
**Task ID:** T5
**Slug:** agent-team-runtime-integration
**Issue:** #24
**类型:** backend
**Batch:** 5
**依赖:** T4 (agent-team-tool-registration, #23)

---

## 1. 目标

在 `AgentRuntime.create_engine()` 中注入 agent-team 上下文（`db_path`, `agent_id`），使 6 个 agent-team tool 在 Engine 创建后可正常工作。

## 2. 前置条件

- **T3 完成**：`src/tools/agent_team_tools.py` 已实现 `set_agent_team_context(db_path, agent_id)` 和 `_agent_team_ctx: ContextVar`
- **T4 完成**：6 个 tool 已注册到 `_default_registry`，`get_openai_tools()` 包含它们

## 3. 实现步骤

### 3.1 修改 `src/runtime/agent_runtime.py`

**调用位置**：在 `create_engine()` 方法的 `return ReactEngine(...)` 之前注入上下文。

**变更内容**：

1. **新增 import**（文件顶部 `from __future__ import annotations` 之后）：

```python
from pathlib import Path
from src.tools.agent_team_tools import set_agent_team_context
```

2. **在 `create_engine()` 中注入上下文**（在 `permission_callback = ...` 之后、`return ReactEngine(...)` 之前）：

```python
# 注入 agent-team 上下文
db_path = self._resolve_agent_team_db_path()
agent_id = getattr(self._config, "agent_id", None) or "agent-001"
set_agent_team_context(db_path, agent_id)
```

3. **新增辅助方法** `_resolve_agent_team_db_path()`：

```python
def _resolve_agent_team_db_path(self) -> str:
    """将 UnifiedConfig.database.url 转换为 agent-team 可用的文件路径。

    database.url 格式为 "sqlite:///relative/path" 或 "sqlite:////absolute/path"。
    去除协议前缀后解析为绝对路径。
    """
    db_url = self._config.database.url
    if db_url.startswith("sqlite:///"):
        path_part = db_url[len("sqlite:///"):]
        if path_part.startswith("/"):
            return path_part
        workspace = self._config.workspace.dir or "."
        return str(Path(workspace) / path_part)
    return db_url  # 非标准格式时原样返回
```

**修改后的 `create_engine()` 完整代码参考**（仅标注增量）：

```python
async def create_engine(
    self,
    api_key: str | None = None,
    model: str | None = None,
    max_iterations: int | None = None,
) -> ReactEngine:
    await self.start_mcp()
    llm = self.get_llm_client()
    permission_engine = self._permission_engine_factory()
    permission_callback = self._permission_callback_factory()

    # >>> 新增：注入 agent-team 上下文 <<<
    db_path = self._resolve_agent_team_db_path()
    agent_id = getattr(self._config, "agent_id", None) or "agent-001"
    set_agent_team_context(db_path, agent_id)

    return ReactEngine(
        llm_client=llm,
        context_limit=self._config.get_model_context_limit(),
        max_steps=max_iterations if max_iterations else 50,
        permission_engine=permission_engine,
        permission_callback=permission_callback,
        skill_registry=self._skill_registry,
    )
```

### 3.2 新建 `tests/unit/test_agent_team_integration.py`

测试文件路径：`tests/unit/test_agent_team_integration.py`

> **注意**：task-graph 中指定为 `tests/runtime/test_agent_team_integration.py`，但项目现有测试均在 `tests/unit/` 下。此处统一到 `tests/unit/`。如有需要可创建 `tests/runtime/` 子目录，由实现者自行判断。

---

## 4. 接口 / 契约

### 4.1 调用链路

```
AgentRuntime.create_engine()
  → self._resolve_agent_team_db_path()    # "sqlite:///intelliagent.db" → "/abs/path/intelliagent.db"
  → set_agent_team_context(db_path, agent_id)
      → _agent_team_ctx.set((db_path, agent_id))
```

### 4.2 `set_agent_team_context()` 签名

来自 `src/tools/agent_team_tools.py`（T3 产出）：

```python
def set_agent_team_context(db_path: str | None, agent_id: str | None) -> None:
    """设置 agent-team 上下文。

    Args:
        db_path: SQLite 数据库文件的绝对路径（传给 AgentTeamDB）
        agent_id: 当前 Agent 的 ID（用于 send_message / receive_message 等）

    传入 (None, None) 可清除上下文。
    """
```

### 4.3 `_resolve_agent_team_db_path()` 行为

| `database.url` 输入 | 输出（示例） |
|---|---|
| `"sqlite:///intelliagent.db"` | `"{CWD}/intelliagent.db"` 或 `"{workspace.dir}/intelliagent.db"` |
| `"sqlite:////tmp/data.db"` | `"/tmp/data.db"` |
| `"/plain/path.db"` | `"/plain/path.db"`（非标准格式，原样返回） |

### 4.4 `agent_id` 取值策略

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | `self._config.agent_id` | 如果 `UnifiedConfig` 后续添加了此字段 |
| 2 | `"agent-001"` | 硬编码默认值（占位，后续支持动态设置） |

> **设计说明**：`UnifiedConfig` 当前无 `agent_id` 字段。如需正式支持，需在 `UnifiedConfig` 中添加 `agent_id: str = "agent-001"`。当前方案使用 `getattr` + 默认值兜底，无需修改配置模型即可工作。

---

## 5. 测试指引

### 5.1 集成测试：上下文注入验证

**文件**：`tests/unit/test_agent_team_integration.py`

**测试用例列表**：

#### TC1: `test_create_engine_injects_agent_team_context`

```python
"""验证 create_engine() 正确设置 _agent_team_ctx。"""
import asyncio
from pathlib import Path

import src.runtime.agent_runtime as agent_runtime_module
from src.config.unified_config import UnifiedConfig
from src.runtime import AgentRuntime
from src.tools.agent_team_tools import _agent_team_ctx, set_agent_team_context


def test_create_engine_injects_agent_team_context(monkeypatch, tmp_path):
    """AgentRuntime.create_engine() 应注入 (db_path, agent_id) 到 _agent_team_ctx。"""
    # 1. 准备配置：指定 database.url 和 workspace
    db_file = tmp_path / "test.db"
    config = UnifiedConfig.model_validate({
        "database": {"url": f"sqlite:///{db_file}"},
        "workspace": {"dir": str(tmp_path)},
    })

    # 2. 替换 ReactEngine 为 Fake（避免真实依赖）
    class FakeReactEngine:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", FakeReactEngine)

    # 3. 创建 Runtime 并调用 create_engine()
    runtime = AgentRuntime(
        config=config,
        llm_client_factory=lambda: _FakeLLMClient(),
        permission_engine_factory=lambda: _FakePermissionEngine(),
        permission_callback_factory=lambda: _FakePermissionCallback(),
    )
    asyncio.run(runtime.create_engine())

    # 4. 验证上下文被正确设置
    ctx = _agent_team_ctx.get()
    assert ctx is not None, "上下文应被设置"
    db_path, agent_id = ctx
    assert db_path == str(db_file), f"db_path 应为 {db_file}，实际为 {db_path}"
    assert agent_id == "agent-001", f"agent_id 应为默认值 'agent-001'，实际为 {agent_id}"

    # 5. 清理上下文
    set_agent_team_context(None, None)
```

#### TC2: `test_create_engine_with_custom_agent_id`

```python
"""验证从 config 获取自定义 agent_id。"""
def test_create_engine_with_custom_agent_id(monkeypatch, tmp_path):
    db_file = tmp_path / "test.db"
    config = UnifiedConfig.model_validate({
        "database": {"url": f"sqlite:///{db_file}"},
        "workspace": {"dir": str(tmp_path)},
    })
    # 通过 setattr 模拟 UnifiedConfig 有 agent_id 字段的场景
    config.agent_id = "custom-agent-42"  # type: ignore[attr-defined]

    class FakeReactEngine:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", FakeReactEngine)
    runtime = AgentRuntime(
        config=config,
        llm_client_factory=lambda: _FakeLLMClient(),
        permission_engine_factory=lambda: _FakePermissionEngine(),
        permission_callback_factory=lambda: _FakePermissionCallback(),
    )
    asyncio.run(runtime.create_engine())

    ctx = _agent_team_ctx.get()
    assert ctx is not None
    _, agent_id = ctx
    assert agent_id == "custom-agent-42"

    set_agent_team_context(None, None)
```

#### TC3: `test_tool_calls_after_context_injection`

```python
"""验证上下文注入后 tool 可正常调用（轻量集成验证）。"""
def test_tool_calls_after_context_injection(monkeypatch, tmp_path):
    """Engine 创建后，send_message 等 tool 不再返回 CONTEXT_NOT_INITIALIZED。"""
    db_file = tmp_path / "test.db"
    config = UnifiedConfig.model_validate({
        "database": {"url": f"sqlite:///{db_file}"},
        "workspace": {"dir": str(tmp_path)},
    })

    class FakeReactEngine:
        def __init__(self, **kwargs):
            pass

    monkeypatch.setattr(agent_runtime_module, "ReactEngine", FakeReactEngine)
    runtime = AgentRuntime(
        config=config,
        llm_client_factory=lambda: _FakeLLMClient(),
        permission_engine_factory=lambda: _FakePermissionEngine(),
        permission_callback_factory=lambda: _FakePermissionCallback(),
    )
    asyncio.run(runtime.create_engine())

    # 验证 tool 层面：上下文存在，调用 get_contacts 不再返回 CONTEXT_NOT_INITIALIZED
    # 注意：此时 DB 未初始化，tool 会返回 DB 相关错误（如表不存在），
    # 但不应返回 CONTEXT_NOT_INITIALIZED
    import asyncio as aio
    from src.tools.agent_team_tools import get_contacts

    result = aio.run(get_contacts())
    assert "CONTEXT_NOT_INITIALIZED" not in result, (
        f"上下文已注入，不应返回 CONTEXT_NOT_INITIALIZED，实际: {result}"
    )

    set_agent_team_context(None, None)
```

### 5.2 Fake 辅助类（测试文件内定义）

```python
class _FakeLLMClient:
    pass

class _FakePermissionEngine:
    pass

class _FakePermissionCallback:
    pass
```

### 5.3 运行测试

```bash
# 单独运行集成测试
pytest tests/unit/test_agent_team_integration.py -v

# 运行全部测试确保无回归
pytest tests/unit/ -v
```

---

## 6. 验收标准

- [ ] `test_create_engine_injects_agent_team_context` 通过：上下文正确设置为 `(db_path, "agent-001")`
- [ ] `test_create_engine_with_custom_agent_id` 通过：自定义 agent_id 可生效
- [ ] `test_tool_calls_after_context_injection` 通过：上下文注入后 tool 不返回 `CONTEXT_NOT_INITIALIZED`
- [ ] 现有测试无回归：`pytest tests/unit/` 全部通过
- [ ] 6 个 agent-team tool 在 Engine 创建后可被 LLM 正常调用

---

## 7. 注意事项

### 7.1 db_path 解析

- `database.url` 默认值为 `"sqlite:///intelliagent.db"`，需去除 `sqlite:///` 前缀
- 相对路径解析基准为 `workspace.dir`（默认 `"."`，即当前工作目录）
- 不要从 `src/db/engine.py` 导入 `resolve_sqlite_database_path`——该模块顶部导入了 SQLAlchemy，会引入不必要的重依赖
- `_resolve_agent_team_db_path()` 实现为独立辅助方法，逻辑足够简单，无需提取到独立模块

### 7.2 agent_id 默认值

- 当前硬编码 `"agent-001"` 是**占位值**
- 未来需支持：
  - 从环境变量 `AGENT_ID` 读取
  - 或从 `intelliagent.json` 的顶层字段读取（需在 `UnifiedConfig` 中添加 `agent_id: str` 字段）
- 实现者注意：不要在此任务中修改 `UnifiedConfig`——保持变更范围最小

### 7.3 上下文生命周期

- `set_agent_team_context()` 在每次 `create_engine()` 时调用
- 多次调用 `create_engine()` 会覆盖上一次的上下文（最后一次调用生效）
- 测试结束后需显式清理：`set_agent_team_context(None, None)`

### 7.4 与现有代码的兼容性

| 关注点 | 状态 |
|--------|------|
| `create_engine()` 签名不变 | ✅ 无新增参数 |
| `UnifiedConfig` 无需修改 | ✅ 使用 `getattr` 兜底 |
| 不影响 LLMClient / PermissionEngine 创建 | ✅ 在独立步骤执行 |
| 幂等性 | ✅ 多次调用覆盖，无副作用累积 |
| Skill 加载不受影响 | ✅ agent-team 上下文与 skill 路径独立 |

### 7.5 风险点

| 风险 | 应对 |
|------|------|
| `src/tools/agent_team_tools.py` 尚未创建（T3 未完成） | T5 严格依赖 T3/T4，等待前置任务完成 |
| `database.url` 为 `""`（空字符串） | `_resolve_agent_team_db_path()` 对空值原样返回；`AgentTeamDB` 构造时会因路径无效报错，属于预期行为 |
| `_agent_team_ctx` 在并发场景下泄漏 | `ContextVar` 天然 asyncio 安全，每个协程/任务有独立上下文副本 |

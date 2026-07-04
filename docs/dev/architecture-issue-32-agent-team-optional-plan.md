# 开发方案: Issue #32 — 将 Agent Team 从默认主线拆成可选能力

**Project:** architecture-cleanup
**Issue:** #32
**类型:** modularity / configuration
**风险等级:** 高
**建议执行方式:** 先配置开关，再收敛工具注册，最后更新文档

---

## 1. 目标

让 Agent Team 成为显式启用的可选能力，避免默认 coding-agent skeleton 绑定多 Agent 协作业务。

---

## 2. 前置决策

需要维护者确认 `agent_team.enabled` 默认值：

| 默认值 | 优点 | 缺点 |
|---|---|---|
| `False` | 最符合 skeleton 定位，默认工具更轻 | 行为有 breaking change |
| `True` | 对当前用户行为兼容 | 架构收益较弱，后续还要翻转默认值 |

建议：默认 `False`。如果担心破坏现有 demo，可先默认 `True` 并在 README 标注后续将默认关闭。

以下方案按默认 `False` 编写。

---

## 3. 当前切入点

重点文件：

| 文件 | 当前问题 |
|---|---|
| `src/config/unified_config.py` | 无 agent-team feature config |
| `src/tools/registry.py` | 默认注册 Agent Team tools |
| `src/runtime/agent_runtime.py` | 创建 ToolRegistryFactory 时不传 feature 开关 |
| `README.md` | 将 Agent Team tools 列为默认内置工具 |
| `docs/adr/0005-agent-team.md` | 描述已过期，仍说纯 sqlite3 + ContextVar |

建议新增/修改测试：

| 文件 | 用途 |
|---|---|
| `tests/unit/test_unified_config.py` | 覆盖 `agent_team.enabled` 默认值和加载 |
| `tests/unit/test_tool_registry.py` 或新增 `tests/unit/test_tool_registry_factory.py` | 覆盖可选注册 |
| 现有 agent-team tests | 确保启用时行为不变 |

---

## 4. 分阶段实现

### 阶段 0：建立当前工具注册基线

执行：

```bash
uv run pytest tests/unit/test_skill_runtime_integration.py tests/tools/test_agent_team_tools.py --tb=short
```

如果路径不存在或测试名称不同，先用 `uv run pytest tests --tb=short` 确认基线。

---

### 阶段 1：新增配置开关

修改 `src/config/unified_config.py`：

```python
class AgentTeamConfig(BaseModel):
    enabled: bool = False


class UnifiedConfig(BaseModel):
    agent_team: AgentTeamConfig = Field(default_factory=AgentTeamConfig)
```

测试：

- 默认 `UnifiedConfig().agent_team.enabled is False`。
- JSON 中 `{ "agent_team": { "enabled": true } }` 能正确加载。

验证：

```bash
uv run pytest tests/unit/test_unified_config.py --tb=short
```

---

### 阶段 2：调整 ToolRegistryFactory

修改 `ToolRegistryFactory.__init__()`，新增参数：

```python
agent_team_enabled: bool = False
```

修改 `create_default()`：

```python
if self._agent_team_enabled:
    self.register_agent_team_tools(registry)
```

注意：

- `register_agent_team_tools()` 保留为独立方法，便于测试和未来 bundle 化。
- 禁用时不要实例化 `AgentTeamTools`。
- 启用时现有 6 个 tools 的 schema 不变。

验证：

```bash
uv run pytest tests/unit/test_tool_registry.py tests/tools/test_agent_team_tools.py --tb=short
```

---

### 阶段 3：接入 AgentRuntime

修改 `AgentRuntime._create_tool_registry()`：

```python
factory = ToolRegistryFactory(
    session_factory_provider=self._database_runtime.get_session_factory,
    conversation_id_provider=lambda: self.conversation_id,
    agent_id=self._config.agent_id,
    skill_registry=self._skill_registry,
    agent_team_enabled=self._config.agent_team.enabled,
)
```

验证：新增 runtime 或 registry factory 测试：

- 默认 config 下 runtime registry 不包含 Agent Team tools。
- `agent_team.enabled=true` 时包含 6 个 Agent Team tools。

---

### 阶段 4：更新文档和 ADR

修改 `README.md`：

- 内置工具表只列核心工具。
- 新增“可选 Agent Team 工具”小节。
- 给出配置示例：

```json
{
  "agent_team": { "enabled": true }
}
```

修改 `docs/adr/0005-agent-team.md`：

- 更新实现状态。
- 删除或修正纯 `sqlite3` + `ContextVar` 描述。
- 说明当前为可选 tool bundle。

---

## 5. 测试计划

新增/更新测试覆盖：

| 用例 | 断言 |
|---|---|
| 默认配置关闭 Agent Team | `UnifiedConfig().agent_team.enabled is False` |
| 配置开启 Agent Team | JSON 加载后为 `True` |
| 默认 registry 不包含 Agent Team tools | 6 个 tool 名称均不存在 |
| 开启时 registry 包含 Agent Team tools | 6 个 tool 名称均存在 |
| 开启时 schema 不变 | `get_openai_tools()` 包含参数 schema |
| Agent Team tool 行为不变 | 现有 agent-team tests 通过 |

最终验证：

```bash
uv run pytest --tb=short
ruff check .
ruff format --check .
```

---

## 6. 风险与控制

| 风险 | 控制 |
|---|---|
| 默认关闭导致现有 demo 缺工具 | README 明确配置开启方式 |
| 测试依赖默认注册 | 测试中显式开启 `agent_team.enabled` |
| 配置字段命名后续变更 | 保持最小字段，只加 `enabled` |
| ADR 和代码继续漂移 | 同 PR 更新 ADR 0005 |

---

## 7. 完成定义

- Agent Team 默认是否启用有明确测试固定。
- 禁用时不注册 Agent Team tools。
- 启用时现有 Agent Team 行为保持不变。
- README 和 ADR 0005 与实现一致。
- 全量测试和 lint 通过。

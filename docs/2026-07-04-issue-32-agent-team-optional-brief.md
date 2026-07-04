## Agent Brief

**类别：** architecture / modularity
**摘要：** 将 Agent Team 从默认主线拆成可选能力，保持 IntelliAgent 作为轻量 coding-agent skeleton 的核心定位。

**关联 Issue：** [#32](https://github.com/devcxl/intelliagent/issues/32)
**相关 ADR：** `docs/adr/0005-agent-team.md`

---

**当前行为：**

Agent Team 已经是一个独立业务子系统，但目前默认接入主线：

- `src/tools/registry.py:140-146` 默认创建并注册 `AgentTeamTools`。
- `src/tools/registry.py:249-306` 默认注册 6 个 agent-team tools。
- `src/db/models.py:19-31` 定义 `Agent` 模型。
- `src/db/models.py:83-102` 定义 `Relay` 和预留 `AgentMemory` 模型。
- `src/services/agent_team.py:45-149` 实现通讯录和消息中继业务逻辑。
- `README.md:70-79` 将 agent-team tools 列入默认内置工具。

这让默认 coding-agent loop 携带多 Agent 协作业务，降低项目的一眼可解释性。

---

**期望行为：**

Agent Team 应该作为可选能力接入，而不是默认主线的一部分。

目标：

1. 用户可通过配置启用/禁用 Agent Team。
2. 禁用时默认 tool list 不包含 `send_message` / `receive_message` / `get_contacts` / `get_contact_detail` / `create_agent` / `delete_agent`。
3. 禁用时 runtime 不需要创建 `AgentTeamTools`。
4. README 明确区分核心内置工具和可选 Agent Team 工具。
5. ADR 0005 与当前实现保持一致，尤其是当前实现已经不是 ADR 中描述的纯 `sqlite3` + `ContextVar` 方案。

---

**建议配置形态：**

优先使用最小配置，不引入复杂 plugin 系统：

```python
class AgentTeamConfig(BaseModel):
    enabled: bool = False
```

可挂在 `UnifiedConfig`：

```python
agent_team: AgentTeamConfig = Field(default_factory=AgentTeamConfig)
```

如果维护者担心行为变更，可以临时默认 `True`，但这会削弱本 issue 的架构目标。建议在 triage 时明确默认值。

---

**建议实现步骤：**

1. **新增配置模型**
   - 在 `src/config/unified_config.py` 添加 `AgentTeamConfig`。
   - 在 `UnifiedConfig` 上添加 `agent_team` 字段。
   - 为默认值和 JSON 加载补单元测试。

2. **调整工具注册**
   - 修改 `ToolRegistryFactory`，接收 `agent_team_enabled: bool`。
   - 只有启用时才构造 `AgentTeamTools` 并调用 `register_agent_team_tools()`。
   - `register_agent_team_tools()` 函数可保留，作为可选 bundle 的注册入口。

3. **调整 Runtime 组装**
   - `AgentRuntime._create_tool_registry()` 将 `self._config.agent_team.enabled` 传给 factory。
   - 禁用时不应创建 `AgentTeamTools`。

4. **更新文档**
   - README 的内置工具表拆成“核心工具”和“可选 Agent Team 工具”。
   - 更新 ADR 0005：当前实现使用 SQLAlchemy model/repository/service/tool，而不是纯 `sqlite3` 方案。

5. **补测试**
   - 默认禁用时 `ToolRegistryFactory.create_default().list_tool_names()` 不包含 agent-team tools。
   - 启用时包含 6 个 agent-team tools。
   - 现有 agent-team tools 测试通过。

---

**验收标准：**

- [ ] `UnifiedConfig` 支持 `agent_team.enabled`。
- [ ] 默认行为经维护者确认并由测试固定。
- [ ] 禁用 Agent Team 时，默认工具列表不包含 6 个 agent-team tools。
- [ ] 启用 Agent Team 时，6 个工具正常注册并保留现有行为。
- [ ] 禁用 Agent Team 时，runtime 不实例化 `AgentTeamTools`。
- [ ] README 明确说明 Agent Team 是可选能力。
- [ ] ADR 0005 不再描述已经过期的纯 `sqlite3` + `ContextVar` 实现。
- [ ] `uv run pytest --tb=short` 通过。
- [ ] `ruff check .` 和 `ruff format --check .` 通过。

---

**不在范围内：**

- 不重写 Agent Team 的业务逻辑。
- 不实现跨进程或分布式 Agent 通信。
- 不实现完整插件系统。
- 不删除 agent-team 数据表；本 issue 只处理默认注册和运行时耦合。
- 不处理 `AgentMemory` 预留模型；可另开 issue 清理。

---

**人类决策点：**

需要维护者确认 `agent_team.enabled` 默认值。架构上建议默认 `False`，但如果要减少行为变化，可先默认 `True`，再通过后续 breaking-change issue 翻转默认值。

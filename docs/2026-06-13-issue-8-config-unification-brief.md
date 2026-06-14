## Agent Brief

**类别：** enhancement
**摘要：** 引入单一 `intelliagent.json` 配置文件，统一 `.env`、`permissions.json`、`mcp_config.json` 三个分散配置源，支持 `"{env:VAR}"` 环境变量插值语法，不保留向后兼容。

**关联 Issue：** [#8](https://github.com/devcxl/intelliagent/issues/8)
**设计文档：** `docs/config-unification-design.md`

---

**当前行为：**

配置分散在三个独立文件中，使用两种不同的加载机制：

| 配置域 | 加载方式 | 消费方 |
|--------|---------|--------|
| LLM 参数、数据库、工作区路径 | Pydantic Settings 从 `.env` / 环境变量读取 | `AgentRuntime._default_llm_client_factory()` 通过 `getattr(self._settings, "OPENAI_API_KEY")` 等访问 |
| 权限规则 | `load_permission_engine()` 手动 `json.load` 读取 `permissions.json`，失败则 fallback 到硬编码 `DEFAULT_RULES` | `AgentRuntime._default_permission_engine_factory()` |
| MCP 服务器 | `MCPConfig.from_file()` 读取 `mcp_config.json`（有 Pydantic 校验但无插值） | `RunService._get_mcp_config()` 通过 `getattr(settings, "MCP_CONFIG")` 获取文件路径后加载 |

问题：
- JSON 配置文件不支持环境变量引用，敏感信息必须明文写入或割裂到 `.env`
- 新增配置项需同时改 Settings 模型和 JSON 文件，心智负担高
- `permissions.json` 无 schema 校验，字段写错静默 fallback 到默认值
- `RunService._get_mcp_config()` 通过 `getattr` 间接访问 settings 字段，耦合脆弱

---

**期望行为：**

1. **统一配置文件**：所有配置收敛到单一 `intelliagent.json`，结构如下：

```jsonc
{
  "llm": {
    "api_key": "{env:OPENAI_API_KEY}",
    "base_url": "{env:OPENAI_API_BASE}",
    "model": "{env:OPENAI_MODEL:gpt-4o-mini}",
    "reasoning_effort": "{env:OPENAI_REASONING_EFFORT}"
  },
  "workspace": { "dir": "{env:WORKSPACE_DIR:.}" },
  "database": { "url": "{env:DATABASE_URL:sqlite:///intelliagent.db}" },
  "experience_file": "{env:EXPERIENCE_FILE:experiences.json}",
  "permissions": {
    "rules": [
      {"tool": "run_shell", "action": "prompt", "conditions": {"dangerous": true}},
      {"tool": "run_shell", "action": "allow", "conditions": {}}
    ]
  },
  "mcp": {
    "servers": [
      {"name": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"], "env": {}}
    ]
  }
}
```

2. **环境变量插值**：JSON 中所有字符串值支持 `"{env:VAR_NAME}"`（必须存在）和 `"{env:VAR_NAME:default}"`（不存在时用默认值）两种语法。插值在 JSON 加载后、Pydantic 校验前执行。

3. **加载优先级**：真实环境变量 > `intelliagent.json`（含插值展开）> 代码默认值。即：即使 JSON 中写了 `"{env:VAR}"`，如果运行时存在同名环境变量，以环境变量为准。

4. **不保留向后兼容**：旧配置文件（`.env`、`permissions.json`、`mcp_config.json`）已完全废弃，项目仅从 `intelliagent.json` 加载配置。详见 [Issue #10](https://github.com/devcxl/intelliagent/issues/10)。

5. **Schema 校验**：配置文件加载后由 Pydantic model 做完整校验，字段类型错误、缺失必填项时报错而非静默 fallback。

---

**关键接口：**

- `UnifiedConfig` (新增) — 统一配置 Pydantic 模型，包含 `llm`、`workspace`、`database`、`experience_file`、`permissions`、`mcp` 子模型。提供 `load(path)` 类方法完成"读取 → 插值 → 校验"全流程。替代当前 `Settings` 作为配置的唯一入口。

- `interpolate(value: str) -> str` (新增) — 对单个字符串执行 `{env:NAME}` / `{env:NAME:default}` 替换。环境变量不存在且无默认值时抛出 `ValueError`。

- `deep_interpolate(obj: Any) -> Any` (新增) — 递归遍历 dict/list/str 结构，对所有字符串值调用 `interpolate`。

- `LLMConfig` (新增) — 替代 `Settings` 中 `OPENAI_API_KEY`、`OPENAI_API_BASE`、`OPENAI_MODEL`、`OPENAI_REASONING_EFFORT` 四个字段。

- `WorkspaceConfig` (新增) — 替代 `Settings.WORKSPACE_DIR`。

- `DatabaseConfig` (新增) — 替代 `Settings.DATABASE_URL`。

- `PermissionsConfig` / `PermissionRule` (新增) — 替代 `permissions.json` 的手动加载。`PermissionRule` 字段：`tool: str`、`action: str = "prompt"`、`conditions: dict = {}`。

- `Settings` (修改) — 保留但改为从 `UnifiedConfig` 构造的桥接层，或标记为 deprecated。所有 `getattr(self._settings, "XXX")` 调用点改为通过 `UnifiedConfig` 访问。

- `load_permission_engine(config_path, workspace)` (修改) — 新增接受 `PermissionsConfig` 对象的重载，替代从文件路径读取。旧签名保留以兼容。

- `MCPConfig.from_file(path)` (修改) — 新增 `from_unified_config(data: dict)` 类方法，从 `UnifiedConfig.mcp` 字段构造。

- `AgentRuntime.__init__(settings)` (修改) — 参数从 `settings: Any` 改为 `config: UnifiedConfig`，内部工厂方法改为通过 `config.llm.api_key` 等属性访问。

- `RunService._get_mcp_config()` (修改) — 改为从 `UnifiedConfig.mcp` 直接构造 `MCPConfig`，不再通过 `getattr(settings, "MCP_CONFIG")` 间接查找文件路径。

- `get_settings()` / `clear_settings_cache()` (修改) — 改为从 `UnifiedConfig` 构造 `Settings` 桥接对象，或标记为 deprecated。

---

**验收标准：**

- [ ] `env_interpolator` 模块通过单元测试：覆盖 `{env:VAR}` 正常替换、`{env:VAR:default}` 默认值回退、环境变量不存在且无默认值时抛 `ValueError`、嵌套 JSON 结构递归插值、非字符串值原样返回
- [ ] `UnifiedConfig.load("intelliagent.json")` 在文件存在时正确加载并校验所有子配置域
- [ ] `UnifiedConfig.load("intelliagent.json")` 在文件不存在时返回全默认值实例
- [ ] 当 `intelliagent.json` 存在时，`AgentRuntime` 和 `RunService` 从 `UnifiedConfig` 读取配置，不再依赖 `.env` / `permissions.json` / `mcp_config.json`
- [ ] 当 `intelliagent.json` 不存在但旧文件存在时，系统保持现有行为不变，且打印 deprecation warning
- [ ] `intelliagent.json` 中权限规则配置与现有 `permissions.json` 行为一致（相同的规则匹配逻辑）
- [ ] `intelliagent.json` 中 MCP 服务器配置与现有 `mcp_config.json` 行为一致（相同的服务器启动逻辑）
- [ ] 所有已有测试通过（`pytest tests/` 零失败）
- [ ] 提供 `intelliagent.json.example` 模板文件，包含所有配置域的示例和注释

---

**不在范围内：**

- 不修改 `ReactEngine`、`PermissionEngine`、`MCPClientManager` 的核心逻辑
- 不修改 `src/db/` 持久化层
- 不修改 `src/tools/` 工具注册和执行
- 不引入新的外部依赖（仅使用已有的 `pydantic`、`pydantic-settings`）
- 不实现配置热加载（配置仅在启动时加载一次）
- 不修改 CLI 入口的参数解析逻辑
- 不实现配置文件的 JSON Schema 自动生成

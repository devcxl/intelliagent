## Agent Brief

**类别：** enhancement
**摘要：** 重构 PermissionEngine，采用 opencode 风格的 last-match-wins + fnmatch 模式匹配权限机制，废弃旧的 first-match-wins + ConditionStrategy 设计。

**关联 Issue：** [#12](https://github.com/devcxl/intelliagent/issues/12)

**当前行为：**

PermissionEngine 采用 first-match-wins 语义：遍历规则列表，返回第一个匹配规则的 action。规则匹配依赖硬编码的 `ConditionStrategy` 策略类（`dangerous`、`path_in_workspace`、`path_sensitive`），每条规则通过 `tool` 字段精确匹配工具名（支持 `"*"` 通配），通过 `conditions` 字典触发对应策略评估。默认规则硬编码在模块级 `DEFAULT_RULES` 常量中。

主要问题：
- first-match-wins 语义不直观，规则顺序与直觉相反（先定义的反而优先级高）
- 条件系统通过策略类扩展，每新增一种条件需新增一个策略类，扩展性差
- 不支持参数级别的模式匹配（如按文件路径模式拒绝 `.env*`）
- 不支持 external_directory 白名单机制
- 默认规则与 opencode 生态不一致（read 默认 allow、edit/bash 默认 ask、`.env` 默认 deny）

**期望行为：**

1. **Last-match-wins 语义**：规则按定义顺序评估，最后一条匹配的规则生效。后定义的规则优先级更高，符合直觉。

2. **fnmatch 模式匹配**：规则中的 pattern 字段使用 fnmatch 通配符匹配工具名。同时，对于包含路径/文件参数的调用，pattern 也匹配参数值（如 `".env*"` 可匹配任何涉及 `.env` 文件的操作）。

3. **三个动作级别**：
   - `allow`：自动放行，不询问用户
   - `ask`：弹出确认提示，等待用户决定
   - `deny`：直接拒绝，不询问用户

4. **external_directory 支持**：配置中可声明外部目录白名单。当工具操作目标在工作区外但在白名单内时，按 external_directory 规则处理（默认 `ask`）。

5. **内置默认规则**（无用户配置时生效）：
   - `read *` → `allow`（读取类工具默认放行）
   - `.env*` → `deny`（环境变量文件始终拒绝）
   - `edit *` → `ask`（编辑类工具默认询问）
   - `bash *` → `ask`（Shell 执行默认询问）
   - `write *` → `ask`（写入类工具默认询问）
   - `*` → `ask`（其他所有工具默认询问）

6. **无匹配规则时**：默认返回 `ask`。

**关键接口：**

- `PermissionAction` 枚举 — 新增 `ask` 值，废弃 `prompt`。`allow` 和 `deny` 保持不变。
- `Decision` 模型 — 保持 `action: PermissionAction` + `reason: str` 结构不变。
- `Rule` 模型 — **废弃**。引擎内部不再使用 Rule 对象，匹配逻辑直接基于 `(pattern, action)` 对。
- `PermissionRule` 配置模型 — 重构为 `pattern: str` + `action: str`（值为 `"allow" | "ask" | "deny"`），移除 `tool` 和 `conditions` 字段。
- `PermissionsConfig` 配置模型 — 新增 `external_directories: list[str]` 字段，保留 `rules: list[PermissionRule]`。
- `PermissionEngine.__init__()` — 新签名：`(rules: list[tuple[str, str]], workspace: Path, external_directories: list[str] | None = None)`。不再接受 `list[dict]`。
- `PermissionEngine.check(tool_name, args) -> Decision` — 签名不变，内部逻辑改为 last-match-wins + fnmatch。
- `PermissionEngineProtocol.check()` — 签名不变。
- `load_permission_engine(config, workspace) -> PermissionEngine` — 适配新构造函数，从 `PermissionsConfig` 提取 `external_directories`。
- `ConditionStrategy` / `DangerousConditionStrategy` / `PathInWorkspaceConditionStrategy` / `PathSensitiveConditionStrategy` — **全部移除**。
- `_is_dangerous_cmd` / `_is_path_sensitive` / `_is_path_in_workspace` — **移除**（不再需要）。
- `DEFAULT_RULES` 模块级常量 — **移除**，默认规则移入 `PermissionEngine` 类属性。
- `AgentRuntime._default_permission_engine_factory()` — 适配新构造函数。
- `PermissionCallback.on_prompt()` — 签名不变，行为不变。

**验收标准：**

- [ ] Last-match-wins：给定规则 `[("read *", "allow"), ("read *", "deny")]`，`check("read_file", {})` 返回 `deny`
- [ ] fnmatch 工具名匹配：`"read *"` 匹配 `read_file`、`read`；`"git*"` 匹配 `git`、`git_status`
- [ ] fnmatch 参数值匹配：规则 `".env*": "deny"` 对 `check("read_file", {"path": ".env"})` 返回 `deny`
- [ ] 三个动作级别：`allow` 直接放行、`ask` 触发回调、`deny` 直接拒绝
- [ ] 默认规则：无用户配置时，`check("read_file", {"path": "src/main.py"})` 返回 `allow`，`check("bash", {"cmd": "ls"})` 返回 `ask`，`check("read_file", {"path": ".env"})` 返回 `deny`
- [ ] external_directory：配置 `external_directories=["/tmp/safe"]`，`check("read_file", {"path": "/tmp/safe/data.txt"})` 返回 `ask`（不在工作区但在白名单）
- [ ] 无匹配规则：`check("unknown_tool", {})` 返回 `ask`
- [ ] `PermissionRule` 配置模型更新为 `pattern` + `action`，旧字段 `tool`/`conditions` 不再存在
- [ ] `PermissionsConfig` 支持 `external_directories` 字段
- [ ] `load_permission_engine()` 正确传递 `external_directories` 到引擎
- [ ] 所有现有测试文件（`test_permission_engine.py`、`test_condition_strategies.py`、`test_permission_integration.py`）被重写以匹配新行为
- [ ] `PermissionAction.prompt` 不再存在，所有引用改为 `PermissionAction.ask`

**不在范围内：**

- `PermissionCallback` / `CliCallback` 的重命名或重构（`on_prompt` 方法名保持不变）
- `ReactEngine._execute_tool()` 的权限检查流程变更（它只调用 `check()` 并根据 `Decision.action` 分支，这部分逻辑不变）
- 工具注册表（`ToolRegistry`）的变更
- 新增工具或修改现有工具实现
- MCP 相关权限控制
- 权限规则的持久化存储（仍通过 `intelliagent.json` 配置）
- doom_loop 检测机制（默认规则中预留 `ask` 语义，但检测逻辑本身不在本 issue 范围）

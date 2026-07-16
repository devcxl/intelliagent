# ADR：Core-owned 工具契约与 Fail-closed 执行

## 状态

已提议

## 背景

当前 Core 通过 `get_openai_tools()` 和 OpenAI SDK tool-call shape 调用工具。ToolRegistry 返回字符串，错误字符串随后被
ToolExecutor 和 observation event 标记为 success。PermissionEngine 缺失时工具会直接执行，MCP 工具还被默认规则整体 allow。

工具注册、DB/Service 装配、Skills 和 MCP 生命周期同时存在于 `src/tools/registry.py`，导致 Core、Tools、Skills、Runtime
边界互相渗透。

## 决策

### Core 拥有稳定契约

在 `src/core/ports/` 定义：

- `ToolSpec`
- `ToolResult` / `ToolStatus`
- `ToolExecutionContext` / `CancellationToken`
- `ToolRegistryPort`
- `CanonicalMessage` / `LLMResponse` / `ToolCall` / `TokenUsage`
- `LLMClientPort`

Core 不得 import OpenAI/MCP SDK、Tools、Skills、DB、Runtime 或 Config。

### ToolExecutor 留在 Core

ToolExecutor 是唯一权限和执行入口，顺序固定为：

```text
校验 ToolCall -> 获取 ToolSpec -> PathPolicy -> PermissionEngine -> Callback -> CancellationToken -> Registry.invoke
```

必须 fail closed：

- 无 PermissionEngine：deny。
- `ask` 且无 Callback：no-callback。
- `allow`：不要求 Callback。
- deny、参数错误、未知工具、执行异常和取消都返回结构化 ToolResult。
- Adapter 保留 arguments parse error，不得把非法 JSON 转成空 object。
- Engine 在收到 LLM 结果后、ToolExecutor 在 Callback 后和 Registry.invoke 前都必须再次检查 CancellationToken；取消后不得启动新工具。

### PathPolicy 是本地路径硬边界

ToolSpec 通过 `local_path_fields` 声明 Runtime 能直接验证的本地路径。工作区外且不在 external directories 的已声明路径
始终 deny，用户规则不可覆盖。

用户规则仍可覆盖默认 `.env*` 和 MCP 规则。MCP server 内部或未声明资源语义不在本地路径沙箱保证范围内，因此 MCP
默认 ask。

local_path_fields 只支持顶层非空字符串。每个已提供字段都必须验证，Executor 将规范化绝对路径写回 copied arguments 后再调用
handler；文件工具在 I/O 前复用同一 PathPolicy。该边界不承诺抵御本地恶意进程并发替换 symlink 的 TOCTOU 攻击。

### Registry 使用 owner/token

- 同名注册默认失败。
- `register()` 返回 opaque `RegistrationToken`。
- `unregister()` 只接受 token，不按名称删除。
- MCP connection 只回滚或注销本 connection 的 token。
- ToolSpec 保存完整 JSON Schema，不再压平。
- owner 是 `register(..., owner=...)` 的 Registry 元数据，不进入 Core-owned ToolSpec。
- MCP `isError` 必须映射为 ToolStatus.ERROR；structuredContent 使用稳定 JSON，非文本 blocks 只返回 omitted 描述，最终 UTF-8
  content 以带原始字节数的标记确定性截断到 32 KiB。本次不引入 artifact 存储。

### Runtime 是唯一装配位置

- `ToolRegistryFactory` 移到 `src/runtime/tool_assembly.py`。
- `SkillTool` 移到 `src/tools/skill_tool.py`。
- Task/Agent Team 业务通过 Service 注入 Tool adapter。
- `CliCallback` 移到 CLI；配置到 PermissionEngine 的转换留在 Runtime。
- TaskService 在事务重构阶段提前引入；Tools 包最终不 import DB、ORM 或 SQLAlchemy。
- 删除没有已批准功能的 MemoryProtocol/AgentMemory 预留，不影响 Agent Team 可选能力。

## 备选方案

### Runtime PermissionedToolGateway

Core 只依赖一个 gateway，由 Runtime 组合 Registry/Permission/Callback。该方案接口更少，但把安全策略放入 composition root，
容易让其他入口绕过 gateway，也不符合项目“Core owns safety rules”的原则，因此不采用。

### 保持 OpenAI-compatible 专用接口

直接把接口重命名为 OpenAI-compatible 可减少 DTO，但 Core 仍无法独立于 SDK shape，新增 provider 或 fake 时仍需伪造 SDK
对象，因此不采用。

### Registry 继续按名称注销

实现简单，但动态 MCP 重名或重连时可能删除其他 owner 的工具，无法提供可验证生命周期，因此不采用。

## 后果

正面：

- 工具状态、权限拒绝和错误可以端到端保真。
- Core 可用纯 fake 独立测试。
- MCP schema 和动态注册生命周期明确。
- Tools/Skills 循环和 Tools 内装配职责被移除。

负面：

- 现有 ToolDef、字符串响应和测试 fake 需要迁移。
- 公开事件契约会从 answer/error 双轨变为统一 terminal。
- owner/token 和完整 schema 会增加少量注册表代码。

## 与现有 ADR 的关系

- 部分取代 ADR 0003 的模块结构和检查优先级；保留 fnmatch、last-match-wins 和三种动作。
- 部分取代 ADR 0004 的 SkillTool 归属和 Runtime 集成位置；保留 Skill 格式和加载策略。
- 部分取代 ADR 0005 的 AgentMemory 预留和 Tool adapter 具体依赖注入；保留 Agent Team 可选能力及 DB -> Service -> Tool 三层结构。
- 部分取代 ADR 0006 的 ToolDef/ToolRegistryFactory 具体布局；保留 SRP、DI 和 Runtime composition root 原则。

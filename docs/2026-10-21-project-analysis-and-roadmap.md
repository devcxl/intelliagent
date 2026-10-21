# IntelliAgent 项目现状分析与改造建议

> 日期：2026-10-21
> 背景：项目最后一次提交为 2026-07-17。本文档基于对 `src/`（约 7,400 行，其中 GUI 2,100 行）、`tests/`（约 6,000 行 / 423 个测试函数）与 6 篇 ADR 的全量静态分析，并对照 2026 年业内 coding agent harness 的公开实践（O'Reilly harness engineering、Sourcegraph context engineering、Google ADK、Claude Agent SDK / OpenAI Agents SDK）撰写。
>
> 定位参照：`CONTEXT.md` —— "可解释的架构，适合教学与展示"。本文的改造建议以此定位为前提，不主张盲目堆特性。

---

## 1. 项目现状概览

IntelliAgent 是一个基于 ReAct 循环的**编码智能体（Coding Agent）框架**，对标 Claude Code / Codex / OpenCode 的心智模型。

核心链路：

```
CLI/GUI → AgentRuntime(组合根) → ConversationSession → ReactEngine
            → LLMClient(OpenAI SDK) → ToolRegistry → PermissionEngine → SQLite
```

已具备能力：ReAct 循环、文件/Shell/任务工具、fnmatch 权限引擎、SQLAlchemy 异步持久化、MCP 接入、SKILL.md 渐进式技能、可选的 Agent Team 消息表、PyQt5 GUI。

**总体判断**：架构叙事成立、分层清晰、代码可读性好；但离"可在真实仓库上完成任务"有明显距离，主要短板集中在**上下文管理正确性、权限边界、LLM 适配层、持久化一致性**四块。

### 模块规模

| 模块 | 行数 | 评价 |
|---|---:|---|
| `src/gui/` | 2,110 | 可选层，直接依赖 repository，绕过 service |
| `src/tools/` | 1,104 | 抽象正确，schema 转换与输出控制不足 |
| `src/core/` | 634 | ReAct 引擎 + ContextManager + ToolExecutor |
| `src/runtime/` | 610 | 组合根，项目中较成熟的部分 |
| `src/db/` | 499 | 结构清楚，事务/迁移/索引是债务 |
| `src/mcp/` | 326 | "能连上"的水平 |
| `src/skills/` | 314 | 干净够用 |
| `src/config/` | 310 | 单一配置 + env 插值，有阻塞网络调用问题 |
| `src/permission/` | 277 | 模型简洁，边界覆盖不足 |
| `src/cli/` | 258 | — |
| `src/utils/` | 240 | 有死代码（`redact_secrets` 无调用） |
| `src/services/` | 364 | Agent Team 实为消息表 CRUD |
| `src/llm/` + `src/types/` | 343 | 名义上的多 provider |

### 依赖

运行时：`mcp`、`anyio`、`python-dotenv`、`pydantic-settings`、`aiofiles`、`openai>=1.0`、`pyyaml`、`sqlalchemy>=2.0.36`、`aiosqlite`。

问题：`pytest`/`pytest-asyncio` 误放运行时依赖；`httpx` 被 `src/mcp/manager.py` 使用但未声明；无 `alembic`、无 `pytest-cov`。

---

## 2. 对照业内最佳实践：Agent Harness 五要素

2026 年业界共识模型：**Agent Harness = Loop · Tool Execution · Context Management · State · Safety**。

### 2.1 Loop（循环）— 当前 ⭐⭐⭐

**做对的**：async ReAct 循环、按步骤事件流（thought→action→observation→answer）、`max_steps=50` 保护。

**差距**：

| 业内实践 | 现状 |
|---|---|
| token 级流式输出（`stream=True`） | 无。LLM 调用整块返回 |
| 并行 tool calls | 严格串行 `for ... await` |
| 超时 / 取消传播 | 无。`to_thread` 的 LLM 请求取消后线程继续跑；shell 超时不杀进程组 |
| 工具结果真实状态 | **observation 永远硬编码 `"success"`**，权限拒绝/异常也被标成功 |

### 2.2 Tool Execution（工具执行）— 当前 ⭐⭐⭐

**做对的**：注册表非全局单例、统一 JSON 响应、schema 注入、`PathPolicy` 防路径逃逸。

**差距**：

1. **schema 转换丢信息**：`ToolRegistry._to_openai_function` 只支持扁平参数，MCP 的嵌套 `inputSchema`、`enum`、`items` 全被降级 → 模型无法正确构造复杂工具参数（MCP 集成的实质缺陷）。
2. **工具结果无分页**：`read_file` 50k 字符硬截断、无 offset/limit；`run_shell` 无输出上限、无 cwd、非零退出码仍返回 `"ok"`。业内共识："工具设计就是上下文工程"——一次大文件 `cat` 比烂 system prompt 更伤上下文。
3. `edit_file` 的 `oldString.strip()` 破坏缩进精确匹配。
4. **缺 grep/glob 检索工具**——现代编码 agent 的核心能力，目前只能靠 `read_file` 硬读。

### 2.3 Context Management（上下文管理）— 当前 ⭐⭐（最大架构短板）

业内共识（Google ADK "context as compiled view"、Claude Code compaction）：

- 压缩用 **LLM 摘要**，保留目标 / 决策 / 已完成 / 失败尝试，滑动窗口 + 保留最近 N 轮不动
- 压缩是 **session 层的持久化操作**，旧消息真正被裁剪
- token 估算基于**当前 prompt**，配合 prefix caching（system prompt 字节级稳定）

现状差距：

1. 摘要是**纯启发式截断**（每条取前 200 字符），工具输出细节全丢。
2. **压缩在 DB 层完全失效**：`compact_callback` 的 `msg_ids` 永远传空列表 → 旧消息从不删除 → 重启后 `load_history_messages` 重新加载全部历史，压缩效果归零。
3. token 计数用**累计值**而非当前上下文大小，多轮后必然误触发。
4. 压缩后产生多条**空 system message**（部分 provider 会 400）。
5. system prompt 每次调用重建且内容可变（skill 列表变化击穿 prefix cache）。

### 2.4 State（状态）— 当前 ⭐⭐⭐

**做对的**：Repository 模式、async SQLAlchemy、Conversation/Message/Task 分层。

**差距**：

- **无 Alembic 迁移**，只有 `create_all`——一旦有真实用户数据就是硬伤。
- **每个 save 即 commit**，`task_write` 等多步操作非原子，中途失败留半套数据。
- `CONTEXT.md` 宣称 `Run` / `Trace` 是核心领域概念，**但没有对应表和持久化**——可观测性为零（业内标准：OpenTelemetry + 每步 trace）。
- 常用查询缺索引（`messages.conversation_id`、`relays.receiver_id` 等）；`Relay` 无外键。
- `load_history_messages` 会把 `tool_name`/`tool_args` 等非标准字段发给 OpenAI API → 恢复会话有 400 风险。

### 2.5 Safety（安全）— 当前 ⭐⭐

**做对的**：独立权限包、allow/deny/ask 三态、last-match-wins、CLI 确认超时拒绝。

**差距（按严重度）**：

1. **MCP 工具默认全 allow**（`permission/engine.py` 的 `("mcp *", "allow")`）——任何远程 MCP 的破坏性工具零确认。**最优先修复项**。
2. **`.env` 规则可被绝对路径绕过**：`fnmatch(".env*", "/home/you/.env")` 为 False → 绝对路径读 `.env` 被放行，敏感信息泄露。
3. **默认规则名与真实工具名不匹配**：规则写 `bash *`，工具叫 `run_shell` → 用户配置失效。
4. **路径检查只看 `args["path"]`**：`run_shell` 的 `cat /etc/passwd`、MCP 工具的任意参数名全部绕过 PathPolicy。
5. 无审计日志（allow/deny 决策不留痕）、无沙箱、无分级权限模式（plan-only / auto-accept 等业内标配）。

### 2.6 周边差距

- **LLM 适配层是名义上的多 provider**：只有同步 OpenAI SDK + `to_thread`，无 `AsyncOpenAI`、无超时/重试/退避；`ProviderRegistry` 在引擎创建路径上做**同步阻塞 urllib 网络请求**；默认配置下 `model=""` 会直接请求失败；带前缀的 model（如 `deepseek/xxx`）被原样发送。
- **Agent Team 只是消息表 CRUD**：`create_agent` 存的 `allowed_tools`/`model`/`workspace` 无任何消费者，没有 worker / 调度 / 消费循环——不是多智能体协作。
- **Memory 是死代码**：`MemoryProtocol` 已定义但 `src/memory/` 目录不存在，README/CONTEXT 仍在宣传。
- **测试腐烂**：`tests/integration/test_react_engine_e2e.py` 引用已删除的 API（`max_consecutive_repeats`、`summary`），靠 CI 未配 `OPENAI_API_KEY` 而侥幸不红；无覆盖率门槛；关键路径（压缩+DB、权限漏洞、LLM 工厂）无测试。
- **文档漂移**：README 提到不存在的 `ConversationOrchestrator`；`intelliagent.json.example` 使用已废弃的 `llm` 配置块（正确格式是 `model` + `provider`），照抄示例会得到空 API key。

---

## 3. 改造路线图

业内共识（Anthropic "Building Effective Agents"、O'Reilly "Stop Overengineering Your Agent Harness"）：**先修 harness 正确性，不要急着加抽象/加功能**。

### P0 — 正确性与安全（改动小、收益大，建议先做）

| # | 事项 | 涉及位置 |
|---|---|---|
| 1 | observation 事件使用 `ToolExecutionResult.status`，不再硬编码 success | `src/core/react_engine.py` |
| 2 | 修复压缩的 DB 契约：`compact_callback` 传真实 message_ids，或改替换式持久化 | `src/core/react_engine.py`、`src/services/conversation_service.py`、`src/db/` |
| 3 | 权限三漏洞：`.env` 绝对路径、`bash*`→`run_shell` 规则名、MCP 默认改 `ask` | `src/permission/engine.py` |
| 4 | LLM 工厂：修 `model=""`、剥离 provider 前缀、`ProviderRegistry` 移出事件循环 | `src/llm/factory.py`、`src/config/` |
| 5 | 删/重写腐烂的 E2E 测试；修正 `intelliagent.json.example` 旧配置格式 | `tests/integration/`、根目录 |

### P1 — 补齐 harness 核心能力（"能否真实使用"的分水岭）

1. **上下文工程重做**：LLM 摘要压缩 + 保留最近 N 轮 + token 基于当前 prompt + system prompt 字节级稳定（为 prefix caching 铺路）。
2. **原生 async**：换 `AsyncOpenAI`；工具调用超时、取消传播、shell 进程组 kill、输出上限、非零退出码明确报错。
3. **工具 schema 支持嵌套/enum**（至少 MCP 透传）；`read_file` 加 offset/limit 分页；`edit_file` 去掉 `strip()`。
4. **加 grep/glob 检索工具**——编码 agent 的能力上限取决于检索。
5. **DB 工程**：Alembic 迁移 + 多步写入单事务 + 关键索引（`messages.conversation_id` 等）+ `Relay` 外键。
6. 恢复会话时过滤非标准消息字段（`tool_name`/`tool_args`）。

### P2 — 能力跃迁（想清楚再做）

1. token 级流式 + 并行 tool calls。
2. Run/Trace 持久化 + OpenTelemetry 可观测性（`CONTEXT.md` 已定义这两个领域概念）。
3. 重做 Agent Team：引入 worker 消费循环 + subagent 模式。业内共识：subagent 的价值是**上下文隔离**而非并行。
4. Memory 用 LLM 摘要 + 文件式项目记忆（对标 AGENTS.md/SKILL.md 生态）真正实现，或者删除死模块 `src/types/memory.py`。
5. 权限分级模式（plan-only / ask / auto-accept）+ 审计日志。
6. Skill 系统增强：返回 `source_path` 实现 ADR 0004 的第三级引用文件；正文长度限制。
7. GUI 改为经 `ConversationService` 操作会话，移除对 repository 的直接依赖。
8. 清理死代码：`MemoryProtocol`、`redact_secrets`、`AgentMemory`、未消费的配置字段（`small_model`、`enabled_providers`、`ProviderOptions.timeout/headers`）。

---

## 4. 战略建议

项目定位是"**可解释的架构，适合教学与展示**"（`CONTEXT.md` 原话）。据此：

- **不要**追 multi-agent 编排、graph engine 等重特性。O'Reilly 2026 文章核心观点即"别过度工程化 agent harness"：核心循环 131 行 Python 就能写完，价值在**上下文工程和工具边界的打磨**。
- 现有架构叙事成立、代码可读性好，**最值得投入的是把 P0 + P1 做扎实**——让骨架真的能在一个真实仓库上跑完一个任务。这比加十个新特性更有说服力。

## 5. 关键文件索引

- 引擎：`src/core/react_engine.py`、`src/core/context_manager.py`、`src/core/tool_executor.py`、`src/core/events.py`
- 组装：`src/runtime/assembly.py`、`src/runtime/agent_runtime.py`、`src/runtime/conversation_session.py`、`src/runtime/engine_factory.py`
- LLM：`src/llm/llm_client.py`、`src/llm/factory.py`、`src/types/llm.py`
- 工具：`src/tools/registry.py`、`src/tools/file_tools.py`、`src/tools/shell_tool.py`、`src/mcp/manager.py`
- 持久化：`src/db/models.py`、`src/db/engine.py`、`src/services/conversation_service.py`
- 安全：`src/permission/engine.py`、`src/utils/path_policy.py`
- 团队：`src/services/agent_team.py`、`src/tools/agent_team_tools.py`
- 配置：`src/config/`、`intelliagent.json.example`
- 测试：`tests/integration/test_react_engine_e2e.py`（已腐烂）、`tests/unit/test_react_engine.py`

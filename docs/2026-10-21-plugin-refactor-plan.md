# IntelliAgent 插件化重构实施计划

> 日期：2026-10-21
> 状态：待审
> 依据：`docs/2026-10-21-project-analysis-and-roadmap.md`（现状分析）、`CONTEXT.md`（目标态术语）、`docs/adr/0007-plugin-architecture.md`、`docs/adr/0008-default-security-posture.md`、`docs/adr/0009-textual-tui-yaml-config.md`

## 1. 目标一句话

围绕插件架构重建 IntelliAgent：内核只留 Engine + 插件宿主，内置插件仅提供 read/write/bash/edit/grep、mcp、skill、storage，前端换 Textual TUI，配置换 YAML，其余能力（memory、permission 等）由外部插件承载。

## 2. 范围

### 建设

| 项 | 说明 |
|---|---|
| PluginHost | Manifest 校验（`api_version`）、Entry Points 发现、能力注册与查询 |
| 插件契约 | Plugin Protocol + 能力接口：Tool / Hook / Permission / Storage |
| 内置插件 | `read`（offset/limit 分页）/ `write` / `bash`（进程组 kill、输出上限）/ `edit`（精确匹配）/ `grep`（ripgrep 子进程）/ mcp / skill / storage（SQLAlchemy/SQLite） |
| 引擎 | ReAct 循环移植；修 P0 正确性项（observation 真实状态、上下文压缩的持久化契约、token 计数基于当前 prompt）；LLM 经 litellm |
| 前端 | Textual TUI（消息流 + 工具调用折叠 + 编辑器 + 状态栏）；无头模式 |
| 配置 | `intelliagent.yaml` + `plugins:` 段 + env 插值 |
| 持久化实体 | Conversation / Message / Run |

### 删除（不移植）

GUI（`src/gui/`）、task_tools、agent_team（含 Agent/Relay/Task 表）、旧 JSON 配置与 env 插值器旧形态、旧 permission 引擎实现、`src/types/memory.py` 死代码、腐烂的 E2E 测试。

### 显式不做（本轮）

memory 专用能力接口、permission 内置实现、多存储后端抽象、TUI 会话列表/设置面板/主题、插件市场/热加载、token 级流式、并行 tool calls。

## 3. 分阶段实施

每阶段一个可独立评审的 PR（符合 AGENTS.md 单次变更 ≤10 文件的控制线），`[step] → verify` 检查点前置。

### Phase 0 — 基线

- 跑通现有测试，记录通过/失败基线（已知腐烂的 E2E 标记 skip 并登记删除）。
- verify: `uv run pytest` 结果与基线一致。

### Phase 1 — 插件宿主（无业务行为）

- `src/core/plugin_host.py`：Manifest（pydantic）+ Plugin Protocol + 能力注册表 + Entry Points 加载器 + `api_version` 拒绝逻辑。
- 内置插件与外部插件同一契约的注册路径。
- verify: 插件契约测试（发现、加载、版本拒绝、能力查询、冲突处理）全绿。

### Phase 2 — 内置工具插件 + storage 插件

- 五个基本工具按新契约实现（命名：`read` / `write` / `bash` / `edit` / `grep`）；修旧实现缺陷（edit 精确匹配、bash 进程组 kill、read 分页、grep 依赖缺失时可诊断报错）。
- storage 插件：SQLAlchemy/SQLite，实体 Conversation / Message / Run。
- verify: 工具行为测试 + 仓库层测试（含边界与错误路径）。

### Phase 3 — 引擎移植 + LLM

- ReactEngine 移植到插件宿主之上：hook 管线（PreToolUse/PostToolUse/SessionStart）、observation 真实状态、上下文压缩持久化契约修复。
- litellm 接入（`src/llm/`），带超时与重试。
- verify: 引擎单测（fake 插件 + fake LLM）；压缩后 DB 行为回归测试。

### Phase 4 — mcp + skill 内置插件

- MCP 客户端管理器移植为内置插件（工具 schema 完整透传，不降级为扁平参数）。
- skill 加载器移植为内置插件（返回 `source_path`，正文长度限制）。
- verify: mcp/skill 插件契约测试 + schema 透传测试。

### Phase 5 — Textual TUI + 无头模式

- TUI：消息流渲染、工具调用折叠、多行编辑器、状态栏；仅消费引擎事件流。
- 无头模式：`intelliagent run "task"`，stdin 进、事件出。
- verify: TUI 组件测试（Textual pilot）；无头模式端到端（fake LLM）。

### Phase 6 — YAML 配置

- `intelliagent.yaml` 读取、`plugins:` 段、env 插值、pydantic 校验。
- verify: 配置解析测试（非法配置给出可诊断错误）。

### Phase 7 — 删除旧代码 + 收尾

- 删除 GUI、task/agent_team、旧配置、旧 permission、死代码；README 与文档对齐目标态。
- verify: `uv run pytest` 全绿（基线 + 新增测试）；`uv run ruff check` 通过；无头模式在真实仓库冒烟一个任务。

## 4. 移植资产清单

| 旧资产 | 去向 |
|---|---|
| ReAct 循环结构（`react_engine.py`） | Phase 3 移植骨架，修 P0 项 |
| `ContextManager` 压缩设计（ADR 0001） | Phase 3 移植思路，摘要策略改为 LLM 摘要（后续增强，本轮先修持久化契约） |
| `PathPolicy` 路径边界 | Phase 2 工具插件内复用 |
| 权限引擎的 last-match-wins 语义 | 不移植实现；语义写入 permission 插件开发文档，供社区插件参考 |
| `MCPClientManager` | Phase 4 移植，修 schema 降级缺陷 |
| skill 加载器 | Phase 4 移植 |
| 测试意图（权限边界/上下文/仓库层） | 改写为插件契约测试与新模块测试 |

## 5. 风险

| 风险 | 缓解 |
|---|---|
| Entry Points 契约发布后难以变更 | `api_version` 从 1 起算；契约测试先行（Phase 1 先于一切业务代码） |
| 默认无防护（ADR 0008） | README 显著提示；无头模式默认拒绝需要 permission 能力却无插件时给出警告 |
| litellm 行为与旧 OpenAI 直连不一致 | Phase 3 用同一组引擎测试跑 fake 与真实 litellm 双路径 |
| 一次性重构面过大 | 严格按 Phase 切 PR，每阶段可独立回滚；删除动作集中在 Phase 7 |
| Textual 学习成本 | TUI 只消费事件流，与引擎解耦，可独立替换 |

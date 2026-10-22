# IntelliAgent 插件化重构实施计划

> 日期：2026-10-21
> 状态：待审（v2，2026-10-21 修订：引擎改为复刻 pi 设计，见 `docs/adr/0010-replicate-pi-engine.md`）
> 后续：LLM 接入已由 `docs/adr/0011-provider-config-and-native-adapters.md` 取代（provider 配置 + 原生协议适配器，废除 litellm）。
> 依据：`docs/2026-10-21-project-analysis-and-roadmap.md`（现状分析）、`CONTEXT.md`（目标态术语）、`docs/adr/0007-plugin-architecture.md`、`docs/adr/0008-default-security-posture.md`、`docs/adr/0009-textual-tui-yaml-config.md`、`docs/adr/0010-replicate-pi-engine.md`、`docs/pi-engine-principles.md`（引擎蓝本）

## 1. 目标一句话

围绕插件架构重建 IntelliAgent：内核只留 Engine + 插件宿主，内置插件仅提供 read/write/bash/edit/grep、mcp、skill、storage，前端换 Textual TUI，配置换 YAML，其余能力（memory、permission 等）由外部插件承载。

## 2. 范围

### 建设

| 项 | 说明 |
|---|---|
| PluginHost | Manifest 校验（`api_version`）、Entry Points 发现、能力注册与查询 |
| 插件契约 | Plugin Protocol + 能力接口：Tool / Hook / Permission / Storage |
| 内置插件 | `read`（offset/limit 分页，输出限额 + 续读提示）/ `write`（不回灌文件）/ `bash`（进程组 kill、尾部保留 + 全量落盘 offload）/ `edit`（精确匹配，只返回 diff）/ `grep`（ripgrep 子进程，匹配数与行宽限额）/ mcp / skill / storage |
| 引擎 | **复刻 pi 设计**（ADR 0010）：三层分层（纯循环/会话编排/LLM）、双层状态机（stopReason 分类、steering/follow-up 队列）、事件模型至 `message_update` 粒度、**投影式压缩**（追加摘要 + 请求时投影，原始记录不删）、system prompt 分 section 增量 patch、工具流水线（beforeToolCall fail-closed / afterToolCall 可改写）、工具输出限额 + 文件 offload |
| LLM | litellm，**token 级流式**（从原 P2 提前到本轮），usage 逐响应落账 |
| 前端 | Textual TUI（消息流 + **流式增量渲染** + 工具调用折叠 + 编辑器 + 状态栏）；无头模式 |
| 配置 | `intelliagent.yaml` + `plugins:` 段 + env 插值 |
| 持久化实体 | Conversation / Message / Run；**entry 表 + parentId 承载 append-only 语义**，compaction 记录含 first_kept_entry_id 与 prompt checkpoint |

### 删除（不移植）

GUI（`src/gui/`）、task_tools、agent_team（含 Agent/Relay/Task 表）、旧 JSON 配置与 env 插值器旧形态、旧 permission 引擎实现、`src/types/memory.py` 死代码、腐烂的 E2E 测试。

### 显式不做（本轮）

会话树导航 / fork / branch summary、虚拟模型路由、嵌套工具调用（`ctx.executeTool`）、JSONL 文件格式（语义由 SQLite 承载）、extension 的 UI 集成面、memory 专用能力接口、permission 内置实现、多存储后端抽象、TUI 会话列表/设置面板/主题、插件市场/热加载、并行 tool calls（保留串行执行，事件与流水线设计不排斥后续并行）。

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

- 五个基本工具按新契约实现（命名：`read` / `write` / `bash` / `edit` / `grep`），照 pi 的输出规格（见 `docs/pi-engine-principles.md` §5）：read 分页 + 续读提示、bash 尾部保留 + 全量落盘、edit/write 不回灌文件、grep 限额、bash 进程组 kill、edit 精确匹配。
- storage 插件：SQLAlchemy/SQLite，承载 **append-only 语义**：entry 表（id/parent_id/type/timestamp/payload）+ compaction 记录（summary + first_kept_entry_id + prompt checkpoint）；原始 entry 永不删除。
- verify: 工具行为测试（含输出限额与 offload）+ 存储层 append-only/投影查询测试。

### Phase 3 — 引擎（复刻 pi 设计，ADR 0010）+ LLM

按 `docs/pi-engine-principles.md` 逐机制实现：

- 三层分层：纯循环（`src/core/`）/ 会话编排（runtime，hook 包装接入）/ LLM（litellm）。
- 双层循环状态机：stopReason 分类（error/aborted 硬退出、length 截断→工具判失败）、steering/follow-up 消息队列、turn 边界 hook（prepareRequest/prepareNextTurn/finishTurn）。
- 事件模型：`agent/turn/message/tool_execution` 事件族至 `message_update`（流式增量）与 `tool_execution_start`（执行前）粒度。
- 工具流水线：prepareArguments → validate → beforeToolCall（fail-closed，permission 插件挂载点）→ execute → afterToolCall（可改写结果）。
- 投影式压缩：阈值触发（contextWindow - reserve）、保留最近 turn 边界切点、LLM 增量摘要（固定结构，拒绝截断）、写 compaction entry + prompt checkpoint，请求时现算投影；token 计数用 provider 真实 usage + 尾部估算。
- system prompt 分 section 增量 patch，前缀字节稳定。
- litellm 接入：token 级流式、超时/重试、usage 逐响应落账。
- verify: 引擎单测（fake 插件 + fake LLM 双路径）；投影压缩回归（压缩后重启投影不含旧 entry）；stopReason 三分类测试；before hook fail-closed 测试。

### Phase 4 — mcp + skill 内置插件

- MCP 客户端管理器移植为内置插件（工具 schema 完整透传，不降级为扁平参数）。
- skill 加载器移植为内置插件（返回 `source_path`，正文长度限制）。
- verify: mcp/skill 插件契约测试 + schema 透传测试。

### Phase 5 — Textual TUI + 无头模式

- TUI：消息流 + **流式增量渲染**（message_update 驱动）、工具调用折叠、单行输入框（Enter 提交）、状态栏；仅消费引擎事件流。
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
| `ContextManager` 压缩设计（ADR 0001） | **废弃**，由 pi 式投影压缩取代（Phase 3）；ADR 0001 标记 superseded |
| 旧 ReAct 循环（`react_engine.py`） | **废弃**，按 pi 蓝本重写（Phase 3）；事件命名（thought/action/observation）保留为事件族别名 |
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
| pi 复刻与 litellm 行为不一致（usage/流协议差异） | Phase 3 用同一组引擎测试跑 fake 与真实 litellm 双路径 |
| 投影压缩实现复杂（切点选择/checkpoint/增量摘要） | 按 pi 分解为可独立测试的纯函数（cut point 计算、摘要合并、投影构建）；先做无 LLM 的投影正确性测试 |
| 一次性重构面过大 | 严格按 Phase 切 PR，每阶段可独立回滚；删除动作集中在 Phase 7 |
| Textual 学习成本 | TUI 只消费事件流，与引擎解耦，可独立替换 |

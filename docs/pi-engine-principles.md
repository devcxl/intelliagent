# pi 引擎原理分析（复刻参考蓝本）

> 日期：2026-10-21
> 来源：badlogic/pi-mono（npm 包名 `@earendil-works/pi-*`），调研快照 commit `16f5f0a`（2026-10-21 检出）
> 用途：IntelliAgent 2026-10 插件化重构的引擎设计蓝本。复刻范围与取舍见 `docs/adr/0010-replicate-pi-engine.md` 与 `docs/2026-10-21-plugin-refactor-plan.md` Phase 3。

## 0. 分层：三层包，循环层极薄

| 层 | pi 位置 | 职责 | 对应 IntelliAgent |
|---|---|---|---|
| Agent Loop | `packages/agent/src/agent-loop.ts` | 纯循环：请求→解析→执行→回填→继续/结束 | `src/core/`（engine） |
| 会话编排 | `packages/coding-agent/src/core/agent-session.ts` | 持久化、压缩、扩展、重试、模型切换 | runtime 层（session orchestrator） |
| 模型接入 | `packages/ai/src/` | 统一流协议，多 provider 适配 | `src/llm/`（litellm） |

核心原则：**循环只关心"怎么跑"，其余全是外挂**。会话编排通过包装 Agent 的 hook 字段（`beforeToolCall`/`afterToolCall`/`finishTurn`/`prepareRequest`/`prepareNextTurn`）和订阅事件接入，不侵入循环。

## 1. 主循环状态机（`runLoop`）

双层结构：

```
外层循环：follow-up（agent 停止后又来消息）与显式 continuation
  内层循环：一个 assistant 响应 + 其 tool calls/results + steering 消息
    ① prepareRequest        — 每次请求前 hook：上下文投影注入、压缩阈值检查
    ② streamAssistantResponse — 流式消费模型响应（token 级）
    ③ stopReason 分类：
         error/aborted      → 不执行工具，turn_end + agent_end 硬退出
         length（token 截断）→ 所有 tool call 判失败（参数不完整，执行必错，让模型重发）
         正常               → 继续
    ④ executeToolCalls      — before hook → 执行 → after hook
    ⑤ finishTurn           — turn 结束 hook，可返回 continue 要求再跑
```

关键机制：

- **turn 边界**：`turn_start`/`turn_end` 事件划分；`prepareNextTurn` 在 turn 完成后、下一次响应前执行（压缩检查 + system prompt/tool 刷新，可替换 context/model）。
- **steering 与 follow-up 队列**：`steer()` 在当前 turn 工具执行完后、下次 LLM 请求前注入消息（用户运行中插话）；`followUp()` 在 agent 即将停止时注入。支持 `"all"` / `"one-at-a-time"` 消费模式。
- **工具批次终止**：工具结果或 afterToolCall 可返回 `terminate: true`；该批次所有结果都 terminate 才停止循环。
- **工具执行策略**：默认并行（准备阶段顺序、执行并发、结果按原始顺序回填）；`executionMode: "sequential"` 或全局配置切顺序。

## 2. 事件模型：事件即协议

三层事件，粒度远超 thought/action/observation 三元组：

| 层 | 事件 | 用途 |
|---|---|---|
| Agent 层 | `agent_start/end`、`turn_start/end`、`message_start/update/end`、`tool_execution_start/update/end` | 驱动流式渲染与执行拦截 |
| Session 层 | `compaction_start/end`、`queue_update`、`auto_retry_*`、`session_info_changed` | 会话状态可视 |
| Extension 层 | `tool_call`、`tool_result`、`context`、`before_agent_start`、`input` 等 | **可拦截、可修改** |

要点：

- `message_update` 携带流式增量（text_delta/thinking_delta/toolcall_delta），TUI 逐块渲染。
- `tool_execution_start` 在**执行前**发出——这是"执行中"状态与 permission 拦截的基础（对比：先执行后发事件的"先做后播"没有拦截能力）。
- `assistantMessageEvent` 是 provider 流事件的统一词汇：`text_start/delta/end`、`thinking_*`、`toolcall_*`、`done`、`error`。
- TUI 完全由事件驱动：`message_start` 建组件、`message_update` 增量更新、`tool_execution_end` 写最终结果，`requestRender()` 合并重绘。

## 3. 上下文组装

### 3.1 system prompt 是 transcript 的一部分

不是每轮拼接的字符串，而是 transcript 中的 `SystemMessage`：

- 按 **section** 存储：`preamble` / `tools` / `rules` / `docs` / `skills` / `cwd` / `project_context`…
- 后续请求只写**增量 patch**（变化的 section + `toolsAdded`/`toolsRemoved`）。
- 恢复会话时 replay 所有 system 消息即得当前 prompt 与工具集——无需独立状态文件。
- 非 preamble section 包成同名 XML 标签；不支持 mid-conversation system 的 provider 由适配层折叠成单一 leading system。
- **字节级稳定的前缀 → prefix caching 不被击穿**。

### 3.2 每轮请求的上下文 = 现算投影

`prepareRequest` 中用 `buildSessionProjection()` 生成发给模型的消息列表，而非直接用内存 transcript。投影处理：compaction 裁剪、branch summary、context_edit、自定义消息转换。`convertToLlm` 做最终 role 映射（compactionSummary → 带 `<summary>` 包装的 user message 等）。

### 3.3 项目知识按需加载

- context files（`AGENTS.md`/`CLAUDE.md`）：从全局目录 + cwd 向上逐级收集，渲染为 `<project_instructions path="...">`。
- skills：`<available_skills>` 只放 **name/description/location**，模型需要时用 `read` 工具读 SKILL.md 全文——上下文按需加载，不全量塞入。
- `/skill:name` 显式调用时展开成 `<skill name location>` XML 注入。

## 4. 压缩（compaction）：追加摘要 + 重投影

**这是 pi 最值得复刻的设计**：压缩不是删除历史，而是改变未来请求的视图。

```
session 记录（append-only）：
  [msg1]...[msg20][COMPACT: summary, firstKeptEntryId=msg15][msg21]...

发给 LLM 的投影：
  [compaction summary] + [msg15..msg21]     ← msg1~14 只是不再进入视图
```

机制细节：

- **触发**：`当前 token > contextWindow - reserveTokens(16384)`；保留最近 `keepRecentTokens(20000)`，切点选 turn 边界（切在 turn 中间时前缀单独总结，标记 `isSplitTurn`）。
- **token 估算**：优先用 provider 真实 `usage.totalTokens` + 尾部新增消息的 `chars/4` 估算。
- **摘要生成**：独立 summarization prompt，LLM 生成固定结构（Goal / Constraints & Preferences / Progress[DOne/In Progress/Blocked] / Key Decisions / Next Steps / Critical Context）；带上次摘要做**增量更新**；拒绝被截断/调工具的摘要；支持重试。
- **写入**：追加 `CompactionEntry`（summary + firstKeptEntryId + tokensBefore + **systemMessage checkpoint**），原始记录不删。
- **重建**：`buildContextEntries()` 从最新 compaction 取 `[summary] + [firstKeptEntryId 起的记录]`。
- **三种自动场景**：溢出+重试一次（先 context_edit 移除失败的 assistant 再压缩）、溢出不重试、阈值到不重试。
- **可被扩展接管**：`session_before_compact` 可取消或提供自定义摘要。

## 5. 工具执行流水线

单次工具调用（每步可挂钩）：

```
prepareArguments（修复模型畸形参数：JSON 字符串、旧字段名）
→ validate（schema 校验 + coerce，失败给详细错误）
→ beforeToolCall   ← permission 挂载点；返回 {block} 或抛错 = 不执行（fail-closed）
→ execute（流式 onUpdate → tool_execution_update）
→ afterToolCall    ← 可替换 content/details/isError/usage/terminate
→ ToolResultMessage（role=toolResult，含 durationMs/timestamp）
```

### 工具结果大小控制：每个工具自己负责

无全局截断器，各工具按语义选 head/tail：

| 工具 | 策略 |
|---|---|
| `read` | 保留头部 2000 行/50KB + `[Showing lines X-Y of N. Use offset=...]` 分页提示 |
| `bash` | `OutputAccumulator` 保留尾部 2000 行/50KB，**完整输出写临时文件**，返回 `Full output: /tmp/...` |
| `grep` | 100 匹配上限、行 500 字符、整体 50KB |
| `edit`/`write` | 只返回成功消息 + diff details，绝不回灌整个文件 |

`OutputAccumulator`：流式 UTF-8 解码、滚动 tail 限内存、超限自动落盘、读全文超限则头尾保留 + 中间省略标记。

### 嵌套工具调用（本轮不复刻）

`ctx.executeTool()` 走同一套校验/hook；结果不进 transcript，只在父结果上存 bounded 记录。

## 6. 会话存储：append-only 树

- **JSONL**：每行一个 entry，`{id, parentId, timestamp, type}`；首行 header（id/cwd/parentSession）。
- entry 类型：`message` / `compaction` / `branch_summary` / `custom`（不进 LLM 上下文）/ `custom_message`（进上下文）/ `context_edit`（追加式修正某条 entry 对上下文的贡献，不删原记录）/ `usage` / `label` / `session_info`。
- **树**：`parentId` 指向父节点；`/tree` 导航只移动 leaf 指针；`/fork` 复制 root→leaf 路径到新文件（header 记 parentSession）。
- **append-only**：分支不改旧行；加载时流式解析、跳过坏行、版本自动迁移。

**复刻取舍**：IntelliAgent 用 SQLite（存储插件）承载同样的**语义**——entry 表 + parentId 形成树、compaction 记录含 first_kept_entry_id、请求时现算投影、原始记录永不删除；不复刻 `/tree`、`/fork`、JSONL 文件格式本身。

## 7. 模型接入（pi-ai）

- 三层抽象：`Model`（含 api 协议族/contextWindow/cost/promptCache）→ `Provider`（auth + stream）→ `Models`（注册表 + auth 解析）。
- **统一流协议** `AssistantMessageEventStream` 是所有 API adapter 的共同语言；`streamSimple` 永远同步返回 stream，异步 setup 错误也编码进流（`lazyStream`）。
- API adapter（anthropic-messages / openai-completions / openai-responses / google / bedrock...）负责：消息/工具转换、thinking block 兼容、图片降级、孤立 tool call 修复、SSE 解析、usage/cost、prompt cache 控制。
- 虚拟模型（`api: "pi-virtual"`）：请求时路由到物理模型，状态存 session custom entry——**本轮不复刻**。

**复刻取舍**：litellm 已提供等价的多 provider 统一层，我们只需消费其 streaming 接口；但 pi 的"错误进流而非同步抛出""usage 逐响应落账"两条纪律照搬。

## 8. 复刻清单（总结）

照搬：三层分层、双层循环状态机（含 stopReason 分类）、完整事件模型（至 message_update 粒度）、token 级流式、投影式压缩（含 checkpoint/增量摘要/split turn）、system prompt 分 section + 增量 patch、工具流水线（prepare/validate/before fail-closed/after 可改写）、工具输出限额 + 文件 offload、steering/follow-up 消息队列、append-only + parentId 存储语义。

不搬：会话树导航/fork/branch summary、虚拟模型路由、嵌套工具调用、JSONL 文件格式（用 SQLite 承载语义）、extension 的 UI 集成面（`ctx.ui`）。

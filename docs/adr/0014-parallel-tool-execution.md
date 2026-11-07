# ADR 0014: 并行工具调用（无条件并行、不设并发上限）

## 状态

已决策，已实施。取代 `docs/2026-10-21-plugin-refactor-plan.md` 中「并行 tool calls（保留串行执行）」的显式不做。

## 背景

引擎 `_resolve_tool_calls` 逐个 `await` 一批 tool call，实测基础设施早已支持并行：

- `ToolExecutionStart` / `ToolExecutionEnd` 都携带 `tool_call_id`，事件可按 id 关联。
- TUI 的 `_tool_panels` 是 `dict[str, ToolCallPanel]`，按 id 索引，天然容纳并发面板。
- 落库发生在 `Compactor.sync_messages`（turn 边界，按引擎记录顺序串行 append），不在工具执行期；链保持线性，不触发 `latest_leaf_in` 的分叉报错。
- `asyncio.gather` 保序返回，满足 OpenAI / Anthropic 对 tool_result 顺序的要求。
- `ToolPipeline` 无可变共享状态（只有 tools / hooks / sink 三个只读字段）。
- bash 的 offload 文件名用 `tempfile.mkstemp`，无竞争。

即：并行的阻碍完全不在基础设施，只在执行策略。

## 决策

一批 tool call **无条件并行**（`asyncio.gather`），**不设并发上限**，与 Claude Code 的行为对齐。不引入只读/副作用分类，不引入保序屏障。

## 已知后果（显式接受）

这些是该决策的代价，不是遗漏：

1. **顺序依赖可能被破坏**。模型同一批发 `write` + `bash`（写完跑测试）时，`bash` 可能在 `write` 之前执行。缓解责任交给模型自身的 tool call 编排能力与工具输出——不做框架层屏障。
2. **无并发上限的失控面**。一个批次发 20 个 `read` 会同时打开 20 个 fd；`bash` 批次会同时起多个子进程。极端批次下可能触及 fd 上限或内存压力。
3. **事件流的交错顺序不反映调用顺序**。`tool_execution_start` 按批次顺序发出，但 `tool_execution_end` 按实际完成顺序到达；TUI 面板因此可能乱序收束。

## 被否决的方案

- **只读并行 + 副作用串行（保序屏障）**：给 `ToolSpec` 加默认 `False` 的 `read_only`，批次内按顺序切段。收益恰好落在安全的只读区、风险恰好落在串行的破坏区，且成本近零（不改 Manifest、不升 `api_version`、MCP 工具自动降级为串行）。被用户否决——选择完全对齐 Claude Code 的无条件并行。
- **并发上限 `Semaphore(8)`**：被用户否决（「并行不做上限」）。因此 fd / 进程压力由其后果 2 承载。
- **保持串行**：收益明确（多文件 read、read+grep 组合是编码 agent 最高频的并行机会），无理由保留。

## 后续评估触发条件

若实测出现「write 后 bash 读到旧内容」的高频故障，或大批次触发 fd 上限，应重新评估本决策——最可能的落点是引入只读分类 + 保序屏障，而非退回全串行。

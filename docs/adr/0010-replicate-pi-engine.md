# ADR 0010: 复刻 pi 引擎设计

## 状态

已决策，取代原实施计划 Phase 3 的引擎设计（见 `docs/2026-10-21-plugin-refactor-plan.md` Phase 3 修订）。

## 背景

原 IntelliAgent 引擎是"事件命名套用 ReAct、实质为 function-calling 步进循环"的实现，存在结构性缺陷：压缩用累计 token 误触发、压缩与持久化脱节（重启后历史全回）、observation 状态硬编码 success、异常留下未配对 tool_calls、事件"先做后播"不可拦截。经逐行分析 pi（badlogic/pi-mono）的引擎实现（`docs/pi-engine-principles.md`），其设计系统性地优于原设计，且与本项目"可解释的架构"定位高度契合。

## 决策

以 pi 引擎为蓝本**复刻核心机制**到重构后的 core：

- 三层分层：纯循环 / 会话编排（hook 包装接入）/ 模型接入（litellm）。
- 双层循环状态机：stopReason 分类处理（error/aborted 硬退出、length 截断则工具判失败）、steering/follow-up 消息队列、turn 边界 hook。
- 事件模型细到 `message_update`（流式增量）与 `tool_execution_start`（执行前），事件流是协议而非日志；token 级流式输出从原 P2 提前到本轮。
- **投影式压缩**：compaction 是追加摘要记录（含 first_kept_entry_id 与 system prompt checkpoint），原始记录永不删除，上下文每次请求现算投影；token 计数用 provider 真实 usage + 尾部估算。
- system prompt 分 section 存储、增量 patch，保证前缀字节稳定（prefix caching 友好）。
- 工具流水线：prepareArguments → validate → beforeToolCall（fail-closed，即 permission 插件挂载点）→ execute → afterToolCall（可改写结果）。
- 工具输出限额按工具自管（read 分页、bash 落盘 offload、edit/write 不回灌文件）。

**持久化承载**：照搬 append-only 语义但不照搬 JSONL 格式——用 SQLite 存储插件承载 entry 表 + parentId 树语义 + compaction 记录（ADR 0007 的 storage 能力不变）。

## 被否决的方案

- **保留原引擎小改**：两套设计混杂，P0 缺陷的根因（存储与视图不分）无法根治。
- **完全照搬 JSONL 文件存储**：丢 SQL 查询能力，storage 插件失去内容；语义等价即可。
- **连会话树/fork/虚拟模型/嵌套工具调用一起搬**：高级特性对教学项目是负担，显式不做（见实施计划"显式不做"）。

## 后果

- 引擎改造量集中在 Phase 3，但换来 P0 缺陷的根治与 TUI 流式渲染的基础。
- 事件模型与 pi 同构，未来对照 pi 文档/源码排错成本低。
- pi 为 MIT 许可，参考其实现属合规借鉴；代码为按原理重写，非逐行翻译。

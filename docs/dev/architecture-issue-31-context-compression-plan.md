# 开发方案: Issue #31 — 对齐上下文压缩实现与 ADR 0001

**Project:** architecture-cleanup
**Issue:** #31
**类型:** correctness / refactor
**风险等级:** 高
**建议执行方式:** 先确认 ADR 方向，再分阶段实现

---

## 1. 目标

让上下文压缩实现与 `docs/adr/0001-context-summary-compression.md` 一致：75% 阈值触发、确定性摘要、压缩后只保留 instruction prefix 和一个 summary message，并将策略从 `ReactEngine` 中移出。

---

## 2. 前置决策

本 issue 有一个必须确认的人类决策点：

| 选项 | 说明 | 建议 |
|---|---|---|
| A | 按 ADR 0001 修改实现 | 推荐 |
| B | 保留当前 LLM 摘要 + recent messages 策略，并修订 ADR | 不推荐，除非维护者明确要求 |

本开发方案按选项 A 编写。

---

## 3. 当前切入点

重点文件：

| 文件 | 当前问题 |
|---|---|
| `src/core/react_engine.py` | `compact_context()` 直接调用 LLM 摘要，且 100% 阈值触发 |
| `src/services/conversation_service.py` | `compact_messages()` 将摘要保存为 `role="system"` |
| `docs/adr/0001-context-summary-compression.md` | 已定义期望行为 |

建议新增文件：

| 文件 | 责任 |
|---|---|
| `src/core/context_manager.py` | 管理 instruction prefix、messages、压缩触发和 summary |
| `tests/unit/test_context_manager.py` | 覆盖 ADR 0001 的 verification requirements |

---

## 4. 分阶段实现

### 阶段 0：冻结当前行为基线

执行：

```bash
uv run pytest tests/unit/test_react_engine.py tests/integration/test_react_engine_e2e.py --tb=short
```

记录当前压缩相关测试覆盖缺口。不要先改实现。

---

### 阶段 1：实现 ContextManager 骨架

新增 `src/core/context_manager.py`。

建议最小数据结构：

```python
@dataclass
class ContextSummary:
    content: str
    source_message_count: int
    compression_count: int
```

建议最小方法：

```python
class ContextManager:
    def __init__(self, max_context_tokens: int, compact_threshold: float = 0.75) -> None: ...
    def initialize_instructions(self, system_prompt: str, agent_prompt: str, tools_instruction: str) -> None: ...
    def add_user_message(self, content: str) -> None: ...
    def add_assistant_message(self, content: str | None, tool_calls: list[dict[str, Any]] | None = None) -> None: ...
    def add_tool_message(self, tool_call_id: str, content: str) -> None: ...
    def load_history(self, messages: list[dict[str, Any]]) -> None: ...
    def compact_if_needed(self, estimated_tokens: int) -> ContextSummary | None: ...
    def get_messages(self) -> list[dict[str, Any]]: ...
```

验证：先只测 instruction prefix 和 message add/load，不接入 `ReactEngine`。

```bash
uv run pytest tests/unit/test_context_manager.py --tb=short
```

---

### 阶段 2：实现确定性 summary

summary 内容建议固定结构：

```text
当前目标:
- ...

用户约束:
- ...

已完成动作:
- ...

关键观察:
- ...

涉及文件:
- ...

待处理事项:
- ...

下一步建议:
- ...
```

提取策略保持简单：

| message role | 处理方式 |
|---|---|
| `user` | 写入当前目标/用户约束 |
| `assistant` with content | 写入已完成动作 |
| `assistant` with tool_calls | 写入待执行工具调用摘要 |
| `tool` | 写入关键观察，截断长输出 |
| 其他 role | 保守写入关键观察 |

硬性要求：当前任务必须保留在 summary 中。

验证：

```bash
uv run pytest tests/unit/test_context_manager.py --tb=short
```

---

### 阶段 3：接入 ReactEngine

修改 `ReactEngine`：

- 构造时创建 `ContextManager`。
- `add_user_message()` / `add_assistant_message()` / `add_tool_message()` 委托给 context manager，或保留兼容方法但内部转发。
- `_call_llm()` 从 `context_manager.get_messages()` 获取消息。
- `_maybe_compact_context()` 调用 `context_manager.compact_if_needed(self.total_tokens)`。
- 删除 `compact_context()` 中的 LLM 摘要逻辑。

注意：可以保留 `ReactEngine.messages` 只读兼容属性一段时间，但不要继续让外部直接修改它。

验证：

```bash
uv run pytest tests/unit/test_react_engine.py tests/integration/test_react_engine_e2e.py --tb=short
```

---

### 阶段 4：修正持久化压缩语义

修改 `ConversationService.compact_messages()`：

- role 按 ADR 改为普通 model-visible message，推荐 `role="user"`。
- content 使用完整 summary，而不是再次包装成 `以下是被压缩的上下文摘要：...`，避免重复前缀。
- 保持删除旧 messages + 插入 summary 的原子性。若当前 repository commit 粒度无法保证，先保持现状，但在测试中覆盖结果。

验证：新增或更新 conversation service 测试。

---

## 5. 测试计划

新增 `tests/unit/test_context_manager.py`，覆盖：

| 用例 | 断言 |
|---|---|
| 75% 阈值触发 | `estimated_tokens >= max * 0.75` 返回 summary |
| 低于阈值不触发 | 返回 `None` |
| instruction prefix 保持顺序 | system、agent、tools instruction 不丢失 |
| 压缩后只保留 summary | raw user/assistant/tool 不在 summary 外出现 |
| 当前任务保留 | summary 包含最新 user task |
| tool observation 文本化 | 不产生裸 `tool` role message |
| 第二次压缩更新 summary | 不追加多个 summary |
| 不调用 LLM | ContextManager 无 LLM 依赖 |

最终验证：

```bash
uv run pytest --tb=short
ruff check .
ruff format --check .
```

---

## 6. 风险与控制

| 风险 | 控制 |
|---|---|
| summary 丢失任务状态 | 单测强制 current task 出现在 summary |
| OpenAI tool-call protocol 被破坏 | 压缩后不保留 raw tool role |
| 现有历史加载行为变化 | ConversationService 测试覆盖 compact 后 load_history |
| 改动范围过大 | 不同时做 ToolExecutor 拆分和 provider 抽象 |

---

## 7. 完成定义

- `ReactEngine` 不再调用 LLM 生成 summary。
- 压缩阈值为 75%。
- 压缩后上下文形状符合 ADR 0001。
- ADR 0001 verification requirements 有测试覆盖。
- 全量测试和 lint 通过。

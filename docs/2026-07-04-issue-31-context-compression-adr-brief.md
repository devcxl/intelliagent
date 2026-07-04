## Agent Brief

**类别：** architecture / correctness
**摘要：** 对齐上下文压缩实现与 ADR 0001，消除文档和运行时行为不一致。

**关联 Issue：** [#31](https://github.com/devcxl/intelliagent/issues/31)
**设计文档：** `docs/adr/0001-context-summary-compression.md`

---

**当前行为：**

当前压缩逻辑直接写在 `ReactEngine` 中：

- `src/core/react_engine.py:121-159` 使用 `total_tokens >= max_context_tokens` 才触发压缩。
- `compact_context()` 调用当前 `llm_client.chat_async()` 生成摘要。
- 压缩后保留最近 `_RECENT_CONTEXT_MESSAGES = 6` 条原始消息。
- `src/services/conversation_service.py:147-159` 将摘要作为 `role="system"` 的消息写回 DB。

这些行为和 ADR 0001 明确冲突：

- ADR 要求达到 `max_context_tokens * 0.75` 时触发压缩。
- ADR 要求第一版使用确定性摘要，不调用 LLM。
- ADR 要求压缩后只保留 instruction prefix 和一个 summary message。
- ADR 要求 `ReactEngine` 不知道 summary 文本如何产生，只调用 `ContextManager`。

---

**期望行为：**

按 ADR 0001 落地一个可测试的 `ContextManager`。

目标上下文形状：

```text
system prompt
agent prompt
tools instruction
context summary message
```

关键规则：

1. 压缩触发阈值为 `estimated_context_tokens >= max_context_tokens * 0.75`。
2. 第一版摘要是确定性的，不调用 LLM。
3. 压缩后不保留 raw user / assistant / tool 历史。
4. tool observations 被写入 summary 文本，不保留 `tool` role message。
5. 当前任务必须出现在 summary 中。
6. 第二次压缩应更新已有 summary，而不是追加多个 summary。

---

**建议接口：**

```python
@dataclass
class ContextSummary:
    content: str
    source_message_count: int
    compression_count: int


class ContextManager:
    def initialize_instructions(
        self,
        system_prompt: str,
        agent_prompt: str,
        tools_instruction: str,
    ) -> None: ...

    def add_user_message(self, content: str) -> None: ...
    def add_assistant_message(self, content: str | None, tool_calls: list[dict[str, Any]] | None = None) -> None: ...
    def add_tool_message(self, tool_call_id: str, content: str) -> None: ...
    def load_history(self, messages: list[dict[str, Any]]) -> None: ...
    def compact_if_needed(self, estimated_tokens: int, max_tokens: int) -> ContextSummary | None: ...
    def get_messages(self) -> list[dict[str, Any]]: ...
```

实现可以比上面更小，但必须保留清晰 seam：`ReactEngine` 不负责摘要生成。

---

**建议实现步骤：**

1. **新增 ContextManager**
   - 文件建议：`src/core/context_manager.py`。
   - 先迁移 message 维护和 `load_history()`。
   - 保留现有 system prompt + available skills 注入行为，但把拼接逻辑从 `ReactEngine` 移出。

2. **实现确定性 summarizer**
   - 不调用 LLM。
   - 将 user messages 提取为目标/约束。
   - 将 assistant messages 提取为已完成动作/回答。
   - 将 tool messages 提取为关键观察。
   - 控制长度，避免 summary 本身无限增长。

3. **接入 ReactEngine**
   - `_call_llm()` 从 `context_manager.get_messages()` 获取可见上下文。
   - 每轮调用前执行 `context_manager.compact_if_needed(...)`。
   - 如果产生 summary，触发 compact callback 写回 DB。

4. **修正持久化语义**
   - DB 写回 summary 的 role 应与 ADR 对齐。
   - 如果决定继续使用 `system` role，必须先修订 ADR，并解释原因。

---

**验收标准：**

- [ ] 压缩在 75% 阈值触发。
- [ ] 压缩不调用 `llm_client.chat_async()`。
- [ ] 压缩后只保留 instruction prefix 和一个 summary message。
- [ ] raw assistant/tool/user 历史不会在 summary 外保留。
- [ ] 当前用户任务出现在 summary 中。
- [ ] tool observations 在 summary 中以普通文本呈现，不产生裸 `tool` message。
- [ ] 第二次压缩更新已有 summary，不追加多个 summary。
- [ ] `ReactEngine` 不再实现 summary 文本生成。
- [ ] 增加 `ContextManager` 单元测试覆盖 ADR 0001 的 verification requirements。
- [ ] `uv run pytest --tb=short` 通过。

---

**不在范围内：**

- 不引入 vector database。
- 不引入长期记忆系统。
- 不引入后台压缩 worker。
- 不优化 provider prompt-cache。
- 不重构 tool registry 或 permission engine。

---

**人类决策点：**

如果维护者不想按 ADR 0001 实现，而是想保留当前 LLM 摘要和 recent messages 策略，则本 issue 的第一步应改为修订 ADR 0001。不要在未确认的情况下同时修改代码和保留旧 ADR。

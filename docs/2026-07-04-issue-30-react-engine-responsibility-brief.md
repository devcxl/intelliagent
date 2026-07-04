## Agent Brief

**类别：** architecture / refactor
**摘要：** 拆分 `ReactEngine` 的多重职责，让它回到只负责 ReAct 循环编排的核心角色。

**关联 Issue：** [#30](https://github.com/devcxl/intelliagent/issues/30)

---

**当前行为：**

`ReactEngine` 当前是核心循环，但已经承担了多个不应混在一个类里的职责：

| 职责 | 当前位置 | 问题 |
|---|---|---|
| 消息状态管理 | `src/core/react_engine.py` 的 `self.messages`、`add_*_message()`、`load_history()` | core loop 和上下文存储耦合 |
| system prompt 构建 | `_build_system_message()` | engine 直接了解 skill registry 和 prompt 拼接 |
| 上下文压缩 | `compact_context()` / `_maybe_compact_context()` | 压缩策略和 LLM 调用混进 loop |
| 工具权限检查 | `execute_tool()` | engine 直接处理 permission decision 和 callback |
| 工具执行 | `execute_tool()` / `_execute_tool_calls()` | engine 直接依赖 registry 调用细节 |
| OpenAI tool-call 适配 | `_to_tool_call_list()` / `_parse_tool_args()` | core 被 provider response shape 污染 |
| 事件构造 | `_answer_event()` / `_thought_event()` / `_execute_tool_calls()` | event schema 分散在 loop 内部 |

主要证据：

- `src/core/react_engine.py:66-87` 构造函数注入 LLM、tools、permission、skill、compact callback，并维护 message/token 状态
- `src/core/react_engine.py:113-159` 构建 system message 和执行上下文压缩
- `src/core/react_engine.py:164-191` 执行权限检查和工具调用
- `src/core/react_engine.py:197-340` 驱动 ReAct loop、事件生成和 public run API

---

**期望行为：**

`ReactEngine` 应该只做一件事：驱动 ReAct 循环。

推荐目标边界：

1. `ReactEngine`：调用 LLM，判断是否有 tool calls，驱动下一轮或返回最终答案。
2. `ContextManager`：管理 messages、system/instruction prefix、历史加载、压缩触发和可见上下文。
3. `ToolExecutor`：解析 tool call、执行权限检查、调用 tool registry、返回统一工具执行结果。
4. `EventBuilder` 或小函数集合：构造 `thought/action/observation/answer` 事件，避免 loop 内手写字典。

---

**建议实现步骤：**

1. **先提取 ToolExecutor**
   - 新增 `src/core/tool_executor.py`。
   - 输入：tool call dict。
   - 输出：结构化结果，例如 `ToolExecutionResult(tool_name, tool_args, content, status, error)`。
   - 迁移 `execute_tool()` 中的 JSON 参数解析、permission check、permission callback、registry 调用。

2. **再提取事件构造**
   - 保持现有事件字典格式不变。
   - 把 `_answer_event()`、`_thought_event()` 和 observation 构造逻辑搬到独立 helper 或 dataclass 方法。

3. **最后收窄 ReactEngine**
   - `ReactEngine._loop()` 只保留：压缩检查、LLM 调用、响应解析、工具执行、终止判断。
   - 避免本 issue 同时重做上下文压缩策略；上下文压缩细节由 #31 处理。

4. **补测试**
   - 单测 `ToolExecutor` 的 allow / ask approved / ask rejected / deny / invalid JSON / unknown tool。
   - 保持 `tests/unit/test_react_engine.py` 聚焦 loop 行为，不再重复覆盖权限细节。

---

**验收标准：**

- [ ] `ReactEngine` 不再直接调用 `permission_engine.check()`。
- [ ] `ReactEngine` 不再直接调用 `permission_callback.on_prompt()`。
- [ ] `ReactEngine` 不再直接调用 `ToolRegistry.call_tool()`。
- [ ] 工具执行相关异常、权限拒绝、用户拒绝路径由 `ToolExecutor` 单测覆盖。
- [ ] 现有 `thought/action/observation/answer` 事件格式保持兼容。
- [ ] `uv run pytest --tb=short` 通过。
- [ ] `ruff check .` 和 `ruff format --check .` 通过。

---

**不在范围内：**

- 不改变 tool registry 的注册 API。
- 不重写上下文压缩策略；该工作属于 #31。
- 不修改 LLM provider 抽象；OpenAI tool-call shape 的彻底隔离可后续单独做。
- 不改变 CLI 输出格式。

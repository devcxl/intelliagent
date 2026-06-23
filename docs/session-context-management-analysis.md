# 会话上下文管理链路分析

## 整体架构

```
src/main.py                    ← CLI 入口
  └─ src/cli/orchestrator.py   ← Conversation 生命周期编排
       ├─ src/db/manager.py    ← 数据库 Facade
       │    ├─ ConversationRepository  ← conversations 表
       │    ├─ MessageRepository       ← messages 表
       │    ├─ RunRepository           ← runs 表
       │    └─ TraceRepository         ← execution_traces 表
       └─ src/runtime/agent_runtime.py  ← 引擎工厂
            └─ src/core/react_engine.py  ← ReAct 引擎
                 └─ src/core/context_manager.py  ← 上下文管理器
                      ├─ src/core/window_strategies.py  ← 窗口溢出策略
                      └─ src/core/token_estimator.py    ← Token 估算
```

两条平行的上下文管理路径：

1. **运行时上下文**（内存中）：`ContextManager` 维护 messages 列表，引擎循环中实时增删
2. **持久化上下文**（SQLite 中）：`ConversationOrchestrator` + 各 Repository 负责读写

---

## 1. 运行时上下文（ContextManager）

### 1.1 消息结构

`ContextManager` 维护一个 `list[dict]`，每条消息遵循 OpenAI Chat Completion 协议格式：

```python
# system — 指令前缀
{"role": "system", "content": "你是一个代码开发助手。"}
{"role": "system", "content": "你的任务是理解用户需求..."}  # agent_prompt
{"role": "system", "content": "可用工具通过 function calling..."}  # tools_instruction

# user — 用户输入
{"role": "user", "content": "用户任务描述"}

# assistant — 模型回复（可能带 tool_calls）
{"role": "assistant", "content": "...", "tool_calls": [...]}

# tool — 工具执行结果
{"role": "tool", "tool_call_id": "call_xxx", "content": "..."}
```

### 1.2 初始化流程

```python
# ContextManager.initialize(task, history_context=None, seed_messages=None)
# 1. 清空所有状态
self._messages = []
self._num_turns = 0

# 2. 构建指令前缀（3 条 system 消息）
instruction_messages = [
    {"role": "system", "content": system_prompt},
    {"role": "system", "content": agent_prompt},
    {"role": "system", "content": tools_instruction},
]

# 3. 构建 user 消息（如果提供了 history_context，拼接到 task 前面）
user_content = task
if history_context:
    user_content = f"{history_context}\n\n现在的新任务是：{task}\n\n请结合上述对话历史，完成新任务。"
self._messages.append({"role": "user", "content": user_content})
```

### 1.3 ReAct 循环中的上下文演进

在 `ReactEngine._loop()` 中，每轮迭代：

```
1. compact_if_needed()         ← 检查是否达到阈值，触发压缩
2. llm_client.chat_async()     ← 发送当前 messages 给 LLM
3. add_assistant_message()     ← 追加模型回复（含 tool_calls）
4. for each tool_call:
     _execute_tool()           ← 执行工具
     add_tool_message()        ← 追加工具结果
5. 如果没有 tool_calls，循环结束
```

消息列表的演进形态：

```
初始:  [system, system, system, user(task)]
第1轮: [system, system, system, user(task), assistant(tool_call), tool(result)]
第2轮: [system, system, system, user(task), assistant(tool_call), tool(result),
        assistant(tool_call), tool(result)]
...
压缩后: [system, system, system, user(summary)]
```

### 1.4 上下文压缩策略

压缩在每次 LLM 调用前检查，阈值逻辑：

```python
# compact_if_needed()
# 当 current_tokens + extra_tokens >= max_tokens * 0.75 时触发
```

**压缩方式**（`compact_to_summary()`）：

- 保留指令前缀（开头的 system 消息）
- 将后续所有非 summary 消息压缩为一条带摘要的 user 消息
- 摘要格式：
  ```
  以下是已压缩的上下文摘要：
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

**特点**：这是一次性压缩（one-shot summary），不是渐进式丢弃。每次压缩会将所有历史消息合并为一条摘要，后续新消息在此基础上继续累积。

### 1.5 滑动窗口截断

`SlidingWindowStrategy` 是第二层防线，在上下文超出 `max_tokens` 时触发：

- 保留 system 消息
- 保留最早 N 条 user 消息（保留原始任务描述）
- 将剩余消息按 `(assistant + tool)` 成组
- 从最早的消息组开始丢弃，直到 token 数满足要求
- 至少保留 `min_messages` 条

**关键设计**：assistant 和 tool 消息必须成组保留，避免孤立的 tool 消息导致 OpenAI API 拒绝请求。

---

## 2. 跨会话上下文（数据库持久化）

### 2.1 数据模型

五张表，层次关系：

```
users
  │
conversations ──── messages        ← 消息历史
  │
runs ───────────── execution_traces  ← 执行轨迹（thought/action/observation/answer）
```

每条关系：
- 1 个 Conversation 包含多条 Message
- 1 个 Conversation 包含多个 Run
- 1 个 Run 包含多条 Trace

### 2.2 跨会话恢复机制

跨会话的上下文传递 **不是通过恢复原始 messages**，而是通过文本摘要：

```python
# ConversationOrchestrator.setup_conversation()
history_messages = await self._db.get_messages(conversation_id)
history_context = ContextManager.build_history_context(history_messages)

# ContextManager.build_history_context(history_messages)
# 将历史消息格式化为纯文本：
"""
以下是之前的对话历史（供参考上下文）：
---
[USER] 用户上次说的内容...
[ASSISTANT] 模型上次回复的内容...
---
"""

# 然后拼接到新的 user 消息中：
user_content = f"{history_context}\n\n现在的新任务是：{task}\n\n请结合上述对话历史，完成新任务。"
```

### 2.3 持久化时机

| 时机 | 操作 |
|------|------|
| Conversation 创建/恢复时 | 插入/更新 `conversations` 表 |
| Run 开始时 | 创建 `runs` 记录 |
| 用户输入后 | `save_message("user", task)` |
| Agent 完成时 | `save_message("assistant", answer)` |
| 每步执行时 | `save_trace()` → 写入 `execution_traces` |
| 结束时 | 更新 `conversations.status` 和 `runs.status` |

**注意**：tool_calls 和 tool 消息 **没有持久化**到 messages 表，只有 `user` 和 `assistant` 角色被保存。execution_traces 表保存了更细粒度的执行轨迹。

### 2.4 Resume / Rerun 路径

| 入口 | 路径 |
|------|------|
| `--resume` | 加载最近 Conversation 的消息历史 → 构建文本摘要 → 新 Run + 新引擎 + 历史摘要 |
| `--session <id>` | 按 ID 加载 Conversation → 同上 |
| `RunService.resume()` | 检查 run 存在且无冲突 → 新引擎 + 历史摘要 |
| `RunService.rerun()` | 在已有 Conversation 中创建新 Run → 可选关联 source_run_id |

**关键观察**：Resume 不恢复 ContextManager 的状态（包括内部计数器、已压缩的摘要、元数据），而是重新创建引擎，只将历史消息作为文本上下文传入。

---

## 3. 完整数据流

### 3.1 新会话流程

```
main.py 启动
  │
  ▼
ConversationOrchestrator.setup_conversation(task, session_id=None, resume=False)
  ├─ 生成 conv-{timestamp} ID
  ├─ 写入 conversations 表 (status=idle)
  ├─ 从 DB 加载历史消息 → 空列表
  └─ 返回 (conversation_id, history_context=None)
  │
  ▼
orchestrator.save_message("user", task)
  └─ 写入 messages 表
  │
  ▼
orchestrator.create_run(task)
  ├─ 生成 run-{timestamp} ID
  └─ 写入 runs 表 (status=running)
  │
  ▼
orchestrator.execute(task, history_context=None)
  ├─ AgentRuntime.create_engine()
  │    └─ 创建 ReactEngine(内部创建 ContextManager)
  │
  └─ engine.iter_steps(task, history_context=None)
       └─ ContextManager.initialize(task)
            ├─ [system, system, system]
            └─ [user: task]
       │
       └─ ReAct 循环（见 1.3）
  │
  ▼
orchestrator.save_event_trace(seq, event)
  └─ 逐条写入 execution_traces 表
  │
  ▼
orchestrator.save_message("assistant", answer)
  └─ 写入 messages 表
  │
  ▼
orchestrator.finalize(status="finished")
  ├─ 更新 conversations.status = finished
  └─ 更新 runs.status = completed
```

### 3.2 恢复会话流程

```
main.py --resume "新任务"
  │
  ▼
ConversationOrchestrator.setup_conversation(task, session_id=None, resume=True)
  ├─ 从 DB 查最新 Conversation（get_latest_conversation）
  ├─ 更新 conversations.status = running
  ├─ 从 DB 加载所有历史消息（get_messages）
  ├─ 调用 ContextManager.build_history_context(history_messages)
  │    └─ 格式化为纯文本摘要
  └─ 返回 (conversation_id, history_context=文本摘要)
  │
  ▼
orchestrator.save_message("user", task)
  └─ 写入 messages 表
  │
  ▼
engine.iter_steps(task, history_context=文本摘要)
  └─ ContextManager.initialize(task, history_context)
       ├─ [system, system, system]
       └─ [user: "历史摘要\n\n现在的新任务是：{task}\n\n请结合上述对话历史，完成新任务。"]
  │
  ▼
  （后续流程同新会话）
```

---

## 4. 设计特点与局限性

### 4.1 设计特点

| 特性 | 说明 |
|------|------|
| **运行时/持久化分离** | ContextManager 只管理内存中的消息，不直接操作 DB |
| **指令前缀不可压缩** | 3 条 system 消息始终保留，不受压缩影响 |
| **成组截断** | assistant + tool 消息成组处理，避免孤立 tool 消息 |
| **文本摘要传递** | 跨会话上下文以纯文本形式传递，而非恢复原始 messages |
| **快照机制** | ContextManager 支持 snapshot/restore，但当前未被 CLI 流程使用 |
| **分层持久化** | messages 存用户/助手对话，execution_traces 存细粒度执行轨迹 |

### 4.2 局限性

| 问题 | 影响 |
|------|------|
| **跨会话信息丢失** | 跨会话恢复时，历史 messages 被压缩为文本摘要，丢失了 tool_calls 的结构化信息。模型只能看到"之前说了什么"，看不到"之前调用了什么工具、得到了什么结果"的完整上下文 |
| **一次压缩不可逆** | `compact_to_summary()` 是一次性操作，将历史全部压成一条 user 消息。如果后续需要回顾具体细节，信息已丢失 |
| **ContextManager 状态不持久化** | 压缩后的摘要状态 (`_summary`)、轮数 (`_num_turns`)、元数据 (`_metadata`) 都不写入 DB。resume 时从头开始 |
| **消息持久化不完整** | tool_calls 和 tool 角色的消息没有写入 messages 表，execution_traces 虽然保存了，但 resume 时没有被利用 |
| **build_history_context 截断** | 每条消息最多保留 500 字符，超过截断。多轮复杂对话后信息衰减严重 |
| **无上下文版本管理** | 不支持回退到某一历史版本、分支执行、或 diff 对比不同 run 的上下文差异 |

### 4.3 与 Claude Code / OpenCode 的对比

| 维度 | IntelliAgent | Claude Code |
|------|-------------|-------------|
| 跨会话恢复 | 纯文本摘要 | 恢复完整 messages（含 tool 结果） |
| 上下文压缩 | 一次性摘要 + 滑动窗口 | 渐进式摘要 + 保持关键观察 |
| 持久化粒度 | user/assistant 消息 + execution_traces | 完整消息链 |
| Resume 恢复精度 | 重新创建引擎，只带文本 | 恢复完整状态 |

---

## 5. 关键文件一览

| 文件 | 职责 |
|------|------|
| `src/main.py` | CLI 入口，编排整个流程 |
| `src/cli/orchestrator.py` | Conversation 生命周期编排（创建/恢复/执行/结束） |
| `src/runtime/run_service.py` | Run 管理（创建/恢复/重跑/取消） |
| `src/runtime/agent_runtime.py` | 引擎工厂，组装依赖 |
| `src/core/react_engine.py` | ReAct 循环引擎，驱动 LLM 调用和工具执行 |
| `src/core/context_manager.py` | 上下文管理器，消息列表的增删改查和压缩 |
| `src/core/window_strategies.py` | 滑动窗口截断策略 |
| `src/core/token_estimator.py` | Token 估算器 |
| `src/db/manager.py` | 数据库 Facade |
| `src/db/repositories.py` | 各仓储类（Conversation/Message/Run/Trace） |

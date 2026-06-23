# 会话上下文管理链路

## 数据流全景

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           CONTEXT 数据流                                  │
│                                                                          │
│  用户输入                                                                  │
│    │                                                                      │
│    ▼                                                                      │
│  ┌─────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐  │
│  │ main.py │───▶│ Orchestrator │───▶│ AgentRuntime│───▶│ ReactEngine  │  │
│  │  CLI    │    │ 编排层        │    │  引擎工厂    │    │  ReAct循环    │  │
│  └─────────┘    └──────────────┘    └─────────────┘    └──────┬───────┘  │
│       │                                                         │        │
│       │                                                         ▼        │
│       │                                                  ┌─────────────┐ │
│       │                                                  │ContextManager│ │
│       │                                                  │ 内存消息列表  │ │
│       │                                                  └──────┬──────┘ │
│       │                                                         │        │
│       ▼                                                         ▼        │
│  ┌─────────────────┐                                    ┌──────────────┐ │
│  │  DatabaseManager │◀───────────────────────────────────│  Token估算 + │ │
│  │  SQLite 持久化   │     persist/load context           │  窗口截断策略  │ │
│  └─────────────────┘                                    └──────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 链路拆解（聚焦数据在各层的形态变化）

### 第 1 层：main.py — 入口

```
输入:  task="重构 UserService"
       flags: --resume / --session <id> / (无)
       ────────────────────────────────────────────────
  ┌──── 调用 orchestrator 的 4 个阶段 ────┐
  │                                       │
  │  1. setup_conversation()  ──→  conv_id, history_context   │
  │  2. save_message("user")  ──→  DB.messages               │
  │  3. create_run()          ──→  DB.runs                   │
  │  4. execute()             ──→  stream events             │
  │     save_event_trace()    ──→  DB.execution_traces       │
  │     save_message("assistant") → DB.messages              │
  │  5. finalize()            ──→  DB 更新状态                │
  └──────────────────────────────────────────────────────────┘
```

### 第 2 层：Orchestrator.setup_conversation() — 关键分叉点

```
                  ┌── session_id 指定?
                  │     ├─ 存在 → 复用该 Conversation
                  │     └─ 不存在 → 创建新 Conversation
         ┌────────┤
         │        ├── resume=True?
         │        │     ├─ 有历史 → 恢复最近一次 Conversation
输入─────┤        │     └─ 无历史 → 创建新 Conversation
         │        │
         │        └── 默认 → 创建全新 Conversation
         │
         ▼
   从 DB 加载历史消息:
   messages = db.get_messages(conversation_id)
        │
        ▼
   关键步骤：历史→文本转换
   history_context = ContextManager.build_history_context(messages)
        │
        ▼
   返回 (conversation_id, history_context)
```

### 第 3 层：Orchestrator.execute() → AgentRuntime → ReactEngine → ContextManager

```
execute(task, history_context)
  │
  ▼
runtime = AgentRuntime()
engine = runtime.create_engine()
  │
  ▼
engine 内部:
  self._ctx = ContextManager(system_prompt, max_tokens=128000)
  │
  ▼
engine.iter_steps(task, history_context)
  │
  ▼
ContextManager.initialize(task, history_context)
```

### 第 4 层：ContextManager.initialize() — 消息构建

```
initialize(task, history_context=None, seed_messages=None)
  │
  ├── seed_messages 有值?   ← 代码有但 CLI 当前未用
  │     └─ _messages = seed_messages (直接恢复完整消息列表)
  │
  └── 普通路径:
        │
        ▼
        _instruction_messages() = [
          {"role": "system", "content": "你是一个代码开发助手。"},
          {"role": "system", "content": "你的任务是理解用户需求..."},
          {"role": "system", "content": "可用工具通过 function calling..."},
        ]
        │
        ▼
        history_context 有值?
          ├─ 有:  user_content = "{history_context}\n\n现在的新任务是：{task}\n\n请结合上述对话历史，完成新任务。"
          └─ 无:  user_content = task
        │
        ▼
        _messages = [S, S, S, user(user_content)]
```

**三种场景下 messages 的初始形态**：

```
新会话:
  [S, S, S, user("重构 UserService")]

恢复会话（当前实现）:
  [S, S, S, user("以下是之前的对话历史：\n---\n[USER] xxx\n[ASSISTANT] xxx\n---\n\n现在的新任务是：重构 UserService\n\n请结合上述对话历史，完成新任务。")]

种子恢复（有代码但未使用）:
  [S, S, S, user("任务"),
   assistant("思考", tool_calls=[call_1]),
   tool(call_1, "结果"),
   ...]   ← 完整的结构化消息
```

### 第 5 层：ReactEngine._loop() — 运行时上下文演进

```
┌─────────────────────────────────────────────────────────────────┐
│ 每轮迭代:                                                        │
│                                                                  │
│  ① compact_if_needed()     ── 检查 tokens，超限 75% 则压缩       │
│  ② get_messages() → LLM   ── 发消息给模型                        │
│  ③ add_assistant_message() ── 追加模型回复                       │
│  ④ 有 tool_calls?                                               │
│       ├─ 是: _execute_tool() → add_tool_message() → 回到 ①       │
│       └─ 否: 结束循环                                             │
└─────────────────────────────────────────────────────────────────┘

具体的消息演进（以 3 轮为例）:

初始:   [S, S, S, user("任务描述")]

第1轮:  [S, S, S, user("任务描述"),
         assistant("我先看看代码", tool_calls=[read_file]),
         tool(msg-1, "文件内容...")]

第2轮:  [S, S, S, user("任务描述"),
         assistant("我先看看代码", tool_calls=[read_file]),
         tool(msg-1, "文件内容..."),
         assistant("需要修改这部分", tool_calls=[edit_file]),
         tool(msg-2, "修改成功")]

第3轮:  [S, S, S, user("任务描述"),
         assistant("我先看看代码", tool_calls=[read_file]),
         tool(msg-1, "文件内容..."),
         assistant("需要修改这部分", tool_calls=[edit_file]),
         tool(msg-2, "修改成功"),
         assistant("任务完成，修改了 UserService 的 login 方法")]

         ← 此时如果 tokens 超限 75%，触发压缩
```

### 第 6 层：ContextManager 压缩机制

```
compact_if_needed()
  │
  ├─ 条件: current_tokens + extra_tokens >= max_tokens × 0.75
  │     └─ 否 → 不做任何事
  │
  └─ 是 → compact_to_summary()
           │
           ▼
           1. 保留 [S, S, S]（指令前缀不被压缩）
           2. 提取所有非指令、非摘要消息
           3. 按角色分类 → 构建摘要文本
           4. _messages = [S, S, S, user("摘要文本")]

压缩后的形态:
  [S, S, S,
   user("以下是已压缩的上下文摘要：
        当前目标:
        - 重构 UserService

        已完成动作:
        - 我先看看代码
        - 需要修改这部分...
        - 任务完成，修改了 UserService 的 login 方法

        关键观察:
        - 工具调用 read_file(src/user_service.py)
        - 工具结果 msg-1：文件内容...
        - 工具调用 edit_file(src/user_service.py)
        - 工具结果 msg-2：修改成功")]

第4轮（压缩后继续）:
  [S, S, S,
   user("摘要..."),
   assistant("验证一下修改", tool_calls=[run_test]),
   tool(msg-3, "测试通过")]
```

### 第 7 层：滑动窗口截断

```
只会在 compact_to_summary 后 tokens 仍然超出 max_tokens 时触发

truncate()
  │
  ▼
SlidingWindowStrategy.apply(messages, max_tokens, system_prompt)
  │
  ├─ 保留 system 消息
  ├─ 保留最早 N 条 user 消息
  ├─ 剩余消息按 (assistant + 其对应的 tool) 成组
  ├─ 从最早组开始丢弃，直到 tokens <= max_tokens
  └─ 至少保留 min_messages 条

为什么必须成组:
  assistant(含tool_calls) → tool(结果1), tool(结果2)
  如果丢弃 assistant 但保留 tool，OpenAI API 会因为孤立的 tool 消息报错
```

### 第 8 层：持久化 — 数据写入 DB

```
execute() 运行中:
  ┌─ 每次 LLM 返回 thought → save_trace(thought)     → execution_traces
  ├─ 每次工具调用 action  → save_trace(action)       → execution_traces
  ├─ 每次工具返回结果     → save_trace(observation)  → execution_traces
  └─ 最终答案            → save_trace(answer)        → execution_traces
                           save_message("assistant") → messages

运行时结束后:
  orchestrator.finalize()
    └─ update_conversation(status="finished")
       └─ update_run(status="completed", current_iteration=N)
```

---

## 跨会话恢复的完整数据流

```
$ python -m src.main --resume "继续重构"

Step 1: Orchestrator.setup_conversation()
─────────────────────────────────────────
  latest = db.get_latest_conversation()         → conv-1718000000
  db.update_conversation(conv-1718000000, status="running")
  history = db.get_messages(conv-1718000000)    → [msg1, msg2, ...]
                                                  ↑
                              只包含 user 和 assistant 角色（tool 消息不存在！）

Step 2: ContextManager.build_history_context(history)
─────────────────────────────────────────────────────
  输入: [
    {"role":"user", "content":"创建项目脚手架"},
    {"role":"assistant", "content":"已创建目录结构..."},
    {"role":"user", "content":"添加单元测试"},
    {"role":"assistant", "content":"已添加 test_user_service.py"}
  ]

  输出:
  """
  以下是之前的对话历史（供参考上下文）：
  ---
  [USER] 创建项目脚手架
  [ASSISTANT] 已创建目录结构...
  [USER] 添加单元测试
  [ASSISTANT] 已添加 test_user_service.py
  ---
  """

  ★ 注意：tool_calls 的信息丢失了！
  模型不知道上次用了什么工具、得到了什么结果

Step 3: ContextManager.initialize(task, history_context)
─────────────────────────────────────────────────────────
  _messages = [
    S, S, S,
    user("以下是之前的对话历史：\n---\n[USER] 创建...\n---\n\n
          现在的新任务是：继续重构\n\n
          请结合上述对话历史，完成新任务。")
  ]

  ★ 注意：这是一个全新的 ContextManager
  上一次的 _summary、_num_turns、_metadata 全部丢失

Step 4: ReactEngine._loop() 开始
─────────────────────────────────
  同新会话流程，不再赘述
```

---

## 数据在各层的存在形式对比

```
┌─────────────────────────────────────────────────────────────────────┐
│                   同一份数据在不同层的表现形式                         │
├────────────┬─────────────────────┬─────────────────┬───────────────┤
│    层       │    数据格式          │    包含信息       │     丢失信息   │
├────────────┼─────────────────────┼─────────────────┼───────────────┤
│ Runtime    │ OpenAI messages     │ system+user+     │ 无            │
│ ContextMgr │ list[dict]          │ assistant+tool   │               │
├────────────┼─────────────────────┼─────────────────┼───────────────┤
│ DB messages│ role + content 文本  │ user/assistant   │ tool_calls    │
│ 表         │                     │ 的纯文本         │ tool 结果     │
├────────────┼─────────────────────┼─────────────────┼───────────────┤
│ DB traces  │ type + data JSON    │ thought/action/  │ 消息关联关系   │
│ 表         │                     │ observation/     │ (谁回复谁)    │
│            │                     │ answer 的结构化  │               │
├────────────┼─────────────────────┼─────────────────┼───────────────┤
│ 跨会话恢复  │ build_history       │ user/assistant   │ tool_calls    │
│ 时传递     │ _context() 纯文本    │ 文本 (截断500字) │ tool 结果     │
│            │                     │                  │ 结构化关系    │
│            │                     │                  │ 压缩状态      │
│            │                     │                  │ 轮数计数      │
└────────────┴─────────────────────┴─────────────────┴───────────────┘
```

---

## 关键类的关系

```
ConversationOrchestrator
  │ 拥有一个 DatabaseManager
  │ 拥有 conversation_id, run_id
  │ 方法: setup_conversation, execute, save_message, save_trace, finalize
  │
  ├── execute() → 创建 AgentRuntime → 创建 ReactEngine
  │                                     │
  │                                     ├── 拥有一个 ContextManager (_ctx)
  │                                     │     ├── _messages: list[dict]
  │                                     │     ├── _summary: ContextSummary
  │                                     │     ├── _num_turns: int
  │                                     │     └── _window_strategy: SlidingWindowStrategy
  │                                     │
  │                                     ├── 拥有一个 LLMClient (_llm_client)
  │                                     ├── 拥有一个 ToolRegistry (_registry)
  │                                     └── 拥有一个 PermissionEngine (_permission_engine)
  │
  └── finalize() → 更新 DB 状态

DatabaseManager (Facade)
  ├── ConversationRepository → conversations 表
  ├── MessageRepository     → messages 表
  ├── RunRepository         → runs 表
  └── TraceRepository       → execution_traces 表
```

---

## 当前问题汇总

```
┌──────────────────────────────────────────────────────────────────────┐
│  问题 1: 跨会话信息降级                                                │
│                                                                      │
│  ContextManager          build_history_context()        跨会话恢复     │
│  messages: [             ────────────────→             纯文本:        │
│    user("重构"),         "以下是之前的对话历史：         user("历史...   │
│    assistant("好的",     ---                              \n新任务")   │
│      tool_calls=[...]),  [USER] 重构                      ↑           │
│    tool("结果1"),        [ASSISTANT] 好的                 结构化→纯文本 │
│    tool("结果2")         ---"                             信息丢失     │
│  ]                                                                    │
│        ↑ 完整结构化                      关键观察完全丢失 ↑            │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  问题 2: tool 消息未持久化                                              │
│                                                                      │
│  db.save_message() 只存 user 和 assistant                             │
│  execution_traces 存了但 resume 时不用                                  │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  问题 3: ContextManager 内部状态不持久化                                 │
│                                                                      │
│  _summary, _num_turns, _metadata 每次重启都丢失                       │
│  虽有 snapshot/restore 机制但未被使用                                   │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│  问题 4: 压缩不可逆                                                    │
│                                                                      │
│  compact_to_summary() 后原始消息永久丢失                               │
│  多层压缩（compression_count）只是叠加摘要，无法回溯                    │
└──────────────────────────────────────────────────────────────────────┘
```

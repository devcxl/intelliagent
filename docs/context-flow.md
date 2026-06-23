# 上下文管理链路

## 全景图：代码调用链 × 数据流

```
用户输入："重构 UserService"
     │
     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│ main.py                                                                  │
│                                                                          │
│  1. orchestrator.setup_conversation("重构 UserService")                   │
│       ├─ db.get_latest_conversation()   # DB: conversations 表            │
│       ├─ db.get_messages(conv_id)       # DB: messages 表                 │
│       └─ build_history_context(messages) → "历史摘要文本"                 │
│                                                                          │
│  2. orchestrator.save_message("user", "重构 UserService")                 │
│       └─ db.save_message()             # DB: messages 表 ← "user:重构"   │
│                                                                          │
│  3. orchestrator.create_run("重构 UserService")                           │
│       └─ db.create_run()               # DB: runs 表                     │
│                                                                          │
│  4. orchestrator.execute("重构", history_context="历史摘要文本")           │
│       │                                                                  │
│       ▼                                                                  │
│    AgentRuntime.create_engine()                                          │
│       │                                                                  │
│       ▼                                                                  │
│    ReactEngine.__init__()                                                │
│       └─ self._ctx = ContextManager(system_prompt, max_tokens=128000)    │
│                                                                          │
│    engine.iter_steps(task, history_context)                              │
│       │                                                                  │
│       ▼                                                                  │
│    ContextManager.initialize(task, history_context)                      │
│       └─ _messages = [S, S, S, user("历史摘要文本\n\n现在新任务是：重构")] │
│                                                                          │
│    ┌────── ReAct 循环 ──────┐                                            │
│    │  while True:           │                                            │
│    │  ① _ctx.compact_if_needed()  # 检查 token 是否超限                  │
│    │  ② llm.chat_async(_ctx.get_messages())  # 发消息给模型              │
│    │  ③ _ctx.add_assistant_message(content, tool_calls)                  │
│    │  ④ 执行工具 → _ctx.add_tool_message(id, result)                    │
│    │     同时: save_trace(thought/action/observation) → DB.traces       │
│    │  ⑤ 无 tool_calls → break                                           │
│    └────────────────────────────────────────────────────┘                │
│                                                                          │
│  5. save_message("assistant", answer)  # DB: messages ← "assistant:..." │
│  6. orchestrator.finalize()                                             │
│       └─ update DB status                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

## 消息列表的演化（这是核心）

```
▼ initialize() 之后
  ┌──┬──────────┬──────────────────────────────────┐
  │# │ role     │ content                          │
  ├──┼──────────┼──────────────────────────────────┤
  │0 │ system   │ "你是一个代码开发助手。"           │
  │1 │ system   │ "你的任务是理解用户需求..."        │
  │2 │ system   │ "可用工具通过 function calling..." │
  │3 │ user     │ "重构 UserService"               │
  └──┴──────────┴──────────────────────────────────┘

▼ 第 1 轮：模型回复（含工具调用）
  ┌──┬──────────┬──────────────────────────────────┐
  │0-3│ (同上)                                      │
  │4 │ assistant│ "我先看看代码"                     │
  │  │          └─ tool_calls: [{name: read_file}]  │
  │5 │ tool     │ "文件内容：class UserService..."   │
  └──┴──────────┴──────────────────────────────────┘

▼ 第 2 轮：模型再次回复
  ┌──┬──────────┬──────────────────────────────────┐
  │0-5│ (同上)                                      │
  │6 │ assistant│ "需要修改 login 方法"              │
  │  │          └─ tool_calls: [{name: edit_file}]  │
  │7 │ tool     │ "修改成功"                         │
  └──┴──────────┴──────────────────────────────────┘

▼ 第 3 轮：模型认为完成，无 tool_calls → 循环结束
  ┌──┬──────────┬──────────────────────────────────┐
  │0-7│ (同上)                                      │
  │8 │ assistant│ "已完成，修改了 login 方法"         │
  └──┴──────────┴──────────────────────────────────┘
```

## Token 超限时发生什么

```
假设 max_tokens = 128000, 75% 阈值 = 96000

第 10 轮时，消息累积了 15 条，estimated_tokens = 100000
                                          ↑ 超了！

compact_if_needed() → 触发 compact_to_summary()

结果：
  [S, S, S, user("以下是已压缩的上下文摘要：
                 当前目标: - 继续重构
                 已完成动作: - 我先看看代码
                             - 需要修改 login 方法
                 关键观察: - 工具调用 read_file(src/...)
                           - 工具结果 msg-xxx: 文件内容...
                           - 工具调用 edit_file(src/...)
                           - 工具结果 msg-xxx: 修改成功")]

压缩后新消息继续累积：
  [S, S, S, user("摘要..."), assistant("验证一下"), tool("测试通过")]
```

## 跨会话恢复时发生了什么

```
当前运行结束后 DB 里有：

  messages 表:
    msg-001  │ user      │ "重构 UserService"
    msg-002  │ assistant │ "我先看看代码"           ← tool_calls 没有保存！
    msg-003  │ assistant │ "需要修改 login 方法"     ← tool_calls 没有保存！
    msg-004  │ assistant │ "已完成，修改了 login 方法"

  execution_traces 表:
    trace-001 │ thought     │ {content: "我先看看代码"}
    trace-002 │ action      │ {tool: "read_file", args: {...}}
    trace-003 │ observation │ {result: "文件内容..."}
    trace-004 │ thought     │ {content: "需要修改 login 方法"}
    trace-005 │ action      │ {tool: "edit_file", args: {...}}
    trace-006 │ observation │ {result: "修改成功"}
    trace-007 │ answer      │ {answer: "已完成..."}

第二天用户 --resume "继续重构"：

  build_history_context(messages) 只读取 messages 表：
    → "以下是之前的对话历史：
       ---
       [USER] 重构 UserService
       [ASSISTANT] 我先看看代码
       [ASSISTANT] 需要修改 login 方法
       [ASSISTANT] 已完成，修改了 login 方法
       ---"

  ★ 模型看不到：上次用了什么工具？看到了什么文件内容？修改了什么？
    这些都只存在 execution_traces 里，但 resume 流程没用它

  引擎重新创建，ContextManager 从零开始：
    → _messages = [S, S, S, user("历史摘要\n\n现在的新任务是：继续重构")]
    → _summary = None, _num_turns = 0  ← 全部重置
```

## 函数调用链摘要

```
main()
  └─ orchestrator.setup_conversation()
       └─ db.get_conversation()
       └─ db.get_messages()
       └─ ContextManager.build_history_context()   ← 静态方法，纯文本转换
  └─ orchestrator.execute()
       └─ AgentRuntime()
       └─ runtime.create_engine()
            └─ ReactEngine(context_manager=ContextManager())
       └─ engine.iter_steps(task, history_context)
            └─ self._ctx.initialize(task, history_context)
            └─ loop:
                 ├─ self._ctx.compact_if_needed()
                 ├─ self.llm_client.chat_async(self._ctx.get_messages())
                 ├─ self._ctx.add_assistant_message(...)
                 ├─ self._execute_tool(...)
                 └─ self._ctx.add_tool_message(...)
  └─ orchestrator.save_event_trace()
       └─ db.save_trace()                          ← execution_traces
  └─ orchestrator.save_message()
       └─ db.save_message()                        ← messages
  └─ orchestrator.finalize()
       └─ db.update_conversation()
       └─ db.update_run()
```

## 一句话总结问题

**运行时** ContextManager 持有完整 messages（含 tool_calls 和 tool 结果），但写入 DB 时只存了 user/assistant 的纯文本，tool 信息进了 `execution_traces` 但恢复时没被使用。跨会话时通过 `build_history_context()` 做了一个有损的纯文本摘要拼接，原始的结构化上下文丢失了。

# 数据表设计

### agent 表

| 字段名    | 数据类型     | 说明     |
| --------- | ------------ | -------- |
| agent_id  | string / int | ID       |
| name      | string       | 名称     |
| desc      | string       | 简介     |
| prompt    | string       | 提示词   |
| workspace | string       | 工作空间 |
| skills[]  | array        | 技能列表 |
| tools[]   | array        | 工具列表 |
| create_at | datetime     | 创建时间 |
| update_at | datetime     | 更新时间 |
| status    | string       | 状态     |

### conversation 表

| 字段名          | 数据类型     | 说明     |
| --------------- | ------------ | -------- |
| conversation_id | string / int | 会话ID   |
| title           | string       | 标题     |
| status          | string       | 状态     |
| members[]       | array        | 成员列表 |

### message 表

| 字段名           | 数据类型     | 说明                                  |
| ---------------- | ------------ | ------------------------------------- |
| message_id       | string / int | 消息ID                                |
| conversation_id  | string / int | 会话ID                                |
| role             | string       | 消息角色（user / assistant / system） |
| content          | string       | 消息正文                              |
| type             | string       | 类型（thought / tool_call / message） |
| is_context_start | boolean      | 是否为上下文起始点                    |
| create_at        | datetime     | 创建时间                              |
| update_at        | datetime     | 更新时间                              |

### todolist 表

| 字段名          | 数据类型     | 说明                             |
| --------------- | ------------ | -------------------------------- |
| todo_id         | string / int | 待办ID                           |
| conversation_id | string / int | 会话ID                           |
| title           | string       | 标题                             |
| context         | string       | 任务内容                         |
| status          | string       | 待办状态（待处理/进行中/已完成） |
| create_at       | datetime     | 创建时间                         |
| update_at       | datetime     | 更新时间                         |

### memory 表

| 字段名    | 数据类型     | 说明         |
| --------- | ------------ | ------------ |
| memory_id | string / int | ID           |
| context   | string       | 记忆内容陈述 |
| create_at | datetime     | 创建时间     |
| update_at | datetime     | 更新时间     |




# buildin_tools
- cmd
- read
- edit
- websearch
- todolist





# 流程优化设计

## 端到端流程（伪代码）

```python
def start(input="用户输入")

    # 创建/获取 Conversation
    if conversation_id is None:
        conversation_id = generate_uuid()
        db.create_conversation(conversation_id, title=task[:50], status="idle")

    # 持久化用户消息
    db.save_message(conversation_id, "user", task)
    messages = db.get_message(conversation_id)
    # 创建 Engine
    engine = runtime.create_engine(seed_message=messages)
    # 启动 ReAct Loop Engine
    result = engine.run()
        engine.run():
            for response, state in _loop(task, history_context):
                if response is None:       # 安全网触发
                    return state
                if not response.tool_calls: # Agent 完成任务
                    return {"success": True, "answer": response.content, ...}


# ============================================================================
# ReactEngine._loop(task, history_context) — 核心循环
# ============================================================================

_loop(messages):
    ctx.initialize(messages)
    tools = registry.get_openai_tools()
    tool_tokens_estimate = estimate_extra_tokens(tools)

    num_turns = 0
    total_tokens = 0
    last_call = None
    consecutive_repeats = 0

    while True:
        # ================================================================
        # A. 安全网检查
        # ================================================================
        if iter_limit and num_turns >= iter_limit:
            yield None, {"success": False, "summary": "达到最大轮数"}

        num_turns += 1

        safety = check_safety(total_tokens, consecutive_repeats)
        # stop 条件：token 超限 OR 连续重复 >= max_consecutive_repeats(5)
        # warn 条件：token >= 80% 上限 OR 连续重复 >= 3
        if safety == "stop":
            yield None, {"success": False, "summary": "安全网触发"}
        if safety == "warn":
            ctx.add_user_message("⚠️ 系统提醒：请尽快总结当前进展并完成任务。")

        # ================================================================
        # B. 上下文压缩
        # ================================================================
        compacted = ctx.compact_if_needed(max_tokens, extra_tokens=tool_tokens_estimate)
        # 触发条件：estimate_tokens() + extra_tokens >= max_tokens * 0.75
        # 压缩逻辑：
        #   1. 保留 instruction 前缀（system prompt 系列）
        #   2. 将后续所有非摘要消息压缩为一条 user 摘要消息
        #   3. 摘要结构：当前目标 / 用户约束 / 已完成动作 / 关键观察 / 下一步建议
        #   4. 设置 _summary 对象（含 compression_count 累加）

        # ================================================================
        # C. LLM 调用
        # ================================================================
        response = llm_client.chat_async(
            messages=ctx.get_messages(),
            temperature=0.3,
            tools=tools,
        )

        # 累计 token 统计
        total_tokens += response.usage.total_tokens

        # ================================================================
        # D. 响应分发
        # ================================================================
        state = {"num_turns": num_turns, "total_tokens": total_tokens, ...}
        yield response, state

        if not response.tool_calls:
            return  # Agent 完成，外层 run() 提取 answer

        # ================================================================
        # E. 工具执行
        # ================================================================
        ctx.add_assistant_message(response.content, tool_calls)

        for tc in response.tool_calls:
            # 重复检测
            if (tc.name, tc.args) == last_call:
                consecutive_repeats += 1
            else:
                consecutive_repeats = 1
            last_call = (tc.name, tc.args)

            # 权限检查
            decision = permission_engine.check(tc.name, tc.args)
            if decision == "deny":
                result = json.dumps({"error": f"权限拒绝: {decision.reason}"})
            elif decision == "ask":
                if not permission_callback.on_prompt(tc.name, tc.args):
                    result = json.dumps({"error": "用户拒绝执行"})
            else:
                result = tool_fn(tc.args)  # 执行工具

            ctx.add_tool_message(tc.id, result)
            memory.add_observation({"tool": tc.name, "args": tc.args, "result": result})


# ============================================================================
# ContextManager.compact_if_needed() — 上下文压缩
# ============================================================================

compact_if_needed(max_tokens, ratio=0.75, extra_tokens=0):
    current = estimate_tokens()  # 粗估：字符数 * 1.3
    if current + extra_tokens < max_tokens * ratio:
        return False  # 不需要压缩
    compact_to_summary()
    return True

compact_to_summary():
    # 1. 保留 instruction 前缀（system 消息）
    instruction = messages[:instruction_count]

    # 2. 收集非摘要消息 → 构建结构化摘要
    source = [m for m in messages[instruction_count:] if not is_summary(m)]

    summary = build_summary(source, old_summary):
        # 提取 user 消息 → "当前目标" / "用户约束"
        # 提取 assistant 消息 → "已完成动作"
        # 提取 tool_calls / tool 消息 → "关键观察"
        # 固定输出结构：目标、约束、已完成、观察、文件、待处理、建议

    # 3. 替换消息列表
    messages = instruction + [{"role": "user", "content": summary}]
    instruction_count = len(instruction)
    compression_count += 1


# ============================================================================
# ContextManager.initialize(task, history_context, seed_messages)
# ============================================================================

initialize(task, history_context, seed_messages):
    if seed_messages:
        # Resume 场景：直接恢复历史消息列表
        messages = list(seed_messages)
        instruction_count = count_system_prefix(messages)
        return

    # 新建场景：构建 [system, system, system, user] 结构
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": agent_prompt},
        {"role": "system", "content": tools_instruction},
    ]
    instruction_count = 3

    if history_context:
        task = f"{history_context}\n\n现在的新任务是：{task}\n\n请结合上述对话历史，完成新任务。"

    messages.append({"role": "user", "content": task})


# ============================================================================
# 数据库持久化流程
# ============================================================================

# conversations 表
db.create_conversation(id, title, task, status="idle")
db.get_conversation(id) → {id, title, task, status, created_at, updated_at}

# messages 表
db.save_message(conversation_id, role="user", content=task)
db.save_message(conversation_id, role="assistant", content=answer)
db.get_messages(conversation_id) → [{role, content, created_at}, ...]

# runs 表
db.create_run(run_id, conversation_id, task_snapshot, status, max_iterations)
db.update_run(run_id, status="completed", current_iteration=n)

# traces 表（流式场景逐条写入）
db.save_trace(trace_id, run_id, iteration=n, type="thought", data={...})
db.save_trace(trace_id, run_id, iteration=n, type="action", data={tool, args})
db.save_trace(trace_id, run_id, iteration=n, type="observation", data={result})


# ============================================================================
# 流式执行流程 (iter_steps)
# ============================================================================

engine.iter_steps(task, history_context):
    for response, state in _loop(task, history_context):
        if response is None:
            yield {"type": "answer", "data": {"answer": "安全网触发"}}
            return

        yield {"type": "thought", "data": {"content": response.content, "has_tool_calls": ...}}

        if response.tool_calls:
            for tc in response.tool_calls:
                yield {"type": "action", "data": {"tool": tc.name, "args": tc.args}}
                result = execute_tool(tc.name, tc.args)
                yield {"type": "observation", "data": {"tool": tc.name, "result": result}}
        else:
            yield {"type": "answer", "data": {"answer": response.content}}
            return
```

## Agent Brief

**类别：** enhancement
**摘要：** 在 ReactEngine、ContextManager、LLMClient、工具执行等关键路径补充 DEBUG 级别日志，以 `模块 - 动作 | key=value` 管道分隔格式追踪执行链路，不改变现有日志行为。

**当前行为：**
- 日志工具 `src/utils/logger.py` 提供基于 Python logging 的简单封装，仅 console handler，默认 INFO 级别
- 现有 11 处日志使用点：react_engine.py（3 处 warning/info）、context_manager.py（3 处 info/warning）、llm_client.py（2 处 debug/error）
- 关键执行路径（循环迭代、上下文压缩、工具调用）无 DEBUG 日志，无法追踪完整执行链路

**期望行为：**
- 在 `LOG_LEVEL=DEBUG` 时，可追踪从任务提交到完成的完整执行链路
- 日志格式统一为 `模块 - 动作 | key=value key=value` 管道分隔风格
- 不改变现有 info/warning/error 日志的级别和内容
- 不引入新框架，仅使用现有 `logger.debug()` 调用

**关键接口：**

| 模块 | 文件 | 关键方法/函数 | 需添加的 DEBUG 日志点 |
|------|------|--------------|---------------------|
| ReactEngine | `src/core/react_engine.py` | `_loop()` | 循环开始（task/token_limit/repeat_limit/iteration_limit）、每轮迭代开始（turn）、LLM 调用前后（msg_count/token_estimate）、compact_if_needed 前后、安全网检查结果、工具执行（tool_name/args_len/result_len）、循环退出原因 |
| ContextManager | `src/core/context_manager.py` | `add_assistant_message()` / `add_tool_message()` / `add_user_message()` | 消息追加（role/content_len） |
| ContextManager | `src/core/context_manager.py` | `compact_if_needed()` | 触发原因（current_tokens/limit/ratio）、压缩前后消息数 |
| ContextManager | `src/core/context_manager.py` | `compact_to_summary()` | 压缩详情（source_msg_count/compression_count） |
| ContextManager | `src/core/context_manager.py` | `truncate()` | 截断前后消息数、token 变化 |
| LLMClient | `src/llm/llm_client.py` | `chat()` | 调用开始（model/msg_count/tool_count）、响应详情（prompt_tokens/completion_tokens/total_tokens/has_tool_calls） |
| ToolRegistry | `src/tools/registry.py` | `call_tool()` | 工具名、参数摘要（args_len） |
| ShellTool | `src/tools/shell_tool.py` | `run_shell()` | 命令、执行时间（ms）、返回码 |
| FileTools | `src/tools/file_tools.py` | `read_file()` / `write_file()` / `edit_file()` | 路径、操作结果（size/returncode） |

**日志格式规范：**
```
模块 - 动作 | key1=value1 key2=value2
```

示例：
```
ReactEngine - 循环开始 | task="修复 bug" token_limit=128000 repeat_limit=5 iteration_limit=10
ReactEngine - 第 3 轮开始 | turns=3 total_tokens=4521
ReactEngine - LLM 调用前 | msg_count=12 token_estimate=3800
LLMClient - 调用开始 | model=gpt-4o-mini msg_count=12 tool_count=5
LLMClient - 响应成功 | prompt_tokens=3200 completion_tokens=150 total_tokens=3350 has_tool_calls=True
ReactEngine - LLM 调用后 | total_tokens=3350 prompt_tokens=3200 completion_tokens=150
ReactEngine - 安全网检查 | result=ok tokens=3350 repeats=0
ReactEngine - 执行工具 | tool=read_file args_len=45
ToolRegistry - 调用工具 | tool=read_file args_len=45
FileTools - 读取文件 | path=/tmp/test.txt size=1024
ReactEngine - 工具结果 | tool=read_file result_len=1024
ContextManager - 追加消息 | role=assistant content_len=150
ContextManager - 追加消息 | role=tool content_len=1024
ContextManager - 压缩检查 | current_tokens=95000 limit=128000 ratio=0.75 triggered=False
ContextManager - 执行压缩 | source_msg_count=20 compression_count=1
ContextManager - 压缩完成 | before_msgs=25 after_msgs=5
ContextManager - 执行截断 | before_msgs=30 after_msgs=20 tokens_before=150000 tokens_after=120000
ReactEngine - 循环退出 | reason=agent_finished turns=5 total_tokens=15000
```

**验收标准：**
- [ ] `LOG_LEVEL=DEBUG` 时，ReactEngine._loop() 的每次迭代输出：循环开始参数、轮次、LLM 调用前后、安全网结果、工具执行、退出原因
- [ ] `LOG_LEVEL=DEBUG` 时，ContextManager 的消息追加操作输出 role 和 content_len
- [ ] `LOG_LEVEL=DEBUG` 时，ContextManager 的 compact_if_needed/compact_to_summary/truncate 输出触发原因和前后对比
- [ ] `LOG_LEVEL=DEBUG` 时，LLMClient.chat() 输出调用开始参数和响应 token 详情
- [ ] `LOG_LEVEL=DEBUG` 时，工具调用输出工具名、参数长度、结果长度
- [ ] `LOG_LEVEL=INFO`（默认）时，不输出任何新增 DEBUG 日志
- [ ] 现有 11 处日志的级别和内容完全不变
- [ ] 日志格式统一为 `模块 - 动作 | key=value` 管道分隔风格
- [ ] 所有新增日志调用使用 `logger.debug()`，不引入新依赖
- [ ] 现有测试全部通过（不因新增日志而破坏）

**不在范围内：**
- 不添加文件日志落地（file handler）
- 不修改日志格式字符串
- 不引入结构化日志框架（如 structlog）
- 不修改与日志无关的代码逻辑
- 不添加日志采样/限流机制
- 不修改 `src/utils/logger.py` 的 setup_logger 实现

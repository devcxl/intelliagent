# ReAct 架构文档

## 📖 概述

IntelliAgent 2.0 使用 **ReAct（Reason-Act-Observe）循环**替代了原有的 PDCA 循环架构。

ReAct 循环更简单、更直接，特别适合代码开发场景（编写代码、运行测试、重构）。

## 🏗️ 架构对比

### PDCA vs ReAct

| 特性 | PDCA 循环 | ReAct 循环 |
|------|-----------|-------------|
| **核心模式** | 计划 → 执行 → 检查 → 改进 | 思考 → 行动 → 观察 → 重复 |
| **循环次数** | 多次循环（3 潮） | 单次循环（多次迭代） |
| **适用场景** | 需要精确规划的任务 | 需要快速响应的任务 |
| **复杂度** | 高（4 个组件） | 中（1 个引擎） |
| **反馈机制** | 循环重试 | 单步失败处理 |
| **响应速度** | 慢（多阶段） | 快（实时迭代） |

### 核心优势

**ReAct 循环的优势**：
1. ✅ **简单直接**：Thought → Act → Observe，单次循环完成任务
2. ✅ **快速响应**：无需完整计划，直接思考并行动
3. ✅ **实时反馈**：每一步都实时显示
4. ✅ **灵活性强**：可以中途调整策略，不依赖初始计划
5. ✅ **适合代码开发**：更接近人类的编程流程

## 🎯 核心组件

### 1. ReactEngine（ReAct 循环引擎）

**职责**：协调整个组件，实现 Reason → Act → Observe 循环

**核心方法**：
- `run(task, max_iterations)`：执行 ReAct 循环
- `_generate_thought()`：生成 LLM 思考
- `_execute_and_observe()`：执行工具并观察结果
- `_create_error_result()`：创建错误结果
- `_create_timeout_result()`：创建超时结果
- `_create_success_result()`：创建成功结果

**输入参数**：
- `llm_client`：LLM 客户端
- `tools`：工具注册中心
- `memory`：记忆管理器
- `context`：上下文管理器
- `max_iterations`：最大迭代次数（默认 10）

**输出结果**：
```json
{
  "success": true/false,
  "summary": "任务摘要",
  "iterations": 迭代次数,
  "answer": "最终答案" | null,
  "observations": [观察结果列表],
  "error": "错误信息" | null,
  "duration": 执行时间（秒）
}
```

### 2. LLMClient（LLM 客户端）

**职责**：封装 OpenAI API 调用，生成 ReAct 思考

**核心方法**：
- `chat(messages, temperature, max_tokens, response_format)`：基础聊天接口
- `generate_react_thought(user_input, observations, available_tools)`：生成 ReAct 思考

**ReAct 提示词特点**：
- 强调代码开发场景（编写代码、运行测试、重构）
- 使用结构化格式（JSON）
- 明确的终止条件（is_complete = true）
- 支持工具列表和参数

### 3. ToolRegistry（工具注册中心）

**职责**：统一管理内置工具和 MCP 外部工具

**支持的协议**：
- 内置工具：直接 Python 函数调用
- MCP：stdio, SSE, HTTP streamable

**内置工具（6 个）**：
- `run_shell`：执行终端命令
- `read_file`：读取文件内容
- `write_file`：写入文件内容
- `list_dir`：列出目录内容
- `delete_file`：删除文件
- `file_exists`：检查文件/目录存在性

### 4. Memory（记忆管理器）

**职责**：管理 ReAct 循环的观察结果和历史经验

**核心功能**：
- `add_observation(obs)`：添加观察结果
- `get_all_observations()`：获取所有观察结果
- `clear_memory()`：清空当前会话的观察
- `save_experience(experience)`：保存成功经验到文件
- `get_similar_experiences(task, top_k)`：获取相似的历史经验

**数据存储**：
- `experiences.json`：历史经验文件
- 观察结果：临时存储在内存中
- 经验数据：持久化到 JSON 文件

### 5. ContextManager（上下文管理器）

**职责**：管理对话历史和环境信息

**核心功能**：
- `add_context(msg)`：添加上下文消息
- `get_context()`：获取最近的上下文（最后 10 条）
- `clear_context()`：清空上下文

## 🔄 执行流程

### ReAct 循环流程

```
用户输入
    ↓
[1] Thought（LLM 思考）
    ↓
[2] Action（执行工具）
    ↓
[3] Observation（观察结果）
    ↓
    [4] 重复直到 is_complete = true 或达到 max_iterations
    ↓
[5] Answer（最终答案）
    ↓
输出结果
```

### 执行示例

**场景：创建 Python 文件并编写测试**

1. **Thought**: "我需要创建一个 Python 文件来实现 Fibonacci 数列"
2. **Action**: {"tool": "write_file", "args": {"path": "fibonacci.py", "content": "..."}}
3. **Observation**: {"status": "ok", "result": "文件已创建"}

4. **Thought**: "现在我需要编写测试来验证实现"
5. **Action**: {"tool": "write_file", "args": {"path": "test_fibonacci.py", "content": "..."}}
6. **Observation**: {"status": "ok", "result": "文件已创建"}

7. **Thought**: "测试已编写完成，任务可以结束"
8. **Answer**: "测试代码已创建并验证通过"

**关键点**：
- 每次迭代都会记录 Thought、Action、Observation
- 最终 Answer 包含任务完成信息
- 支持 99 次最大迭代

## 📊 数据流

```
┌─────────────────┐
│ 用户输入         │
└──────┬────────┘
         │
         ↓
    ┌──────┐
    │ ReactEngine    │
    │              │
    │              ├────→ llm_client (generate_react_thought)
    │              │
    │              ├────→ tools (get_tool)
    │              │
    │              ├────→ memory (add_observation)
    │              │
    │              └────→ context (add_context)
    └───────────────┘
         │
         ↓
    ┌─────────────────┐
│  最终结果         │
└──────────────────┘
```

## 🎯 设计原则

### 1. 简洁性

- **Reason → Act → Observe**：单次循环，易于理解
- **明确的终止条件**：is_complete = true
- **实时反馈**：每一步都记录和显示
- **最小化状态管理**：只保存必要的信息

### 2. 灵活性

- **动态调整策略**：根据观察结果实时思考下一步
- **无需初始计划**：避免 PDCA 的计划生成阶段
- **快速失败恢复**：工具调用失败立即处理

### 3. 可测试性

- **独立的组件**：LLM、Tools、Memory、Context 都可独立测试
- **清晰的接口**：每个组件有明确的输入输出
- **可 Mock**：使用 Mock 对象进行单元测试

## 🚀 错误处理

### 失败场景

1. **LLM 调用失败**：
   - 记录错误日志
   - 返回错误结果
   - 终止循环

2. **工具调用失败**：
   - 记录失败的 Observation
   - 继续循环或根据情况决定
   - 不无限重试（单次失败不重试）

3. **达到最大迭代次数**：
   - 返回超时结果
   - 记录警告日志
   - 保存部分结果到经验

4. **配置错误**：
   - API Key 未配置：明确提示用户
   - 工具不可用：列出可用工具
   - 初始化失败：记录详细错误信息

## 📚 与 PDCA 的区别

### 已移除的组件

- ❌ `planner.py`：计划生成器
- ❌ `checker.py`：质量检查器
- ❌ `actor.py`：改进器
- ❌ `pdca_loop.py`：PDCA 循环控制器
- ❌ `react_loop.py`：简化的 React 循环

### 保留的组件

- ✅ `llm_client.py`：LLM 客户端（扩展了 generate_react_thought 方法）
- ✅ `tool_registry.py`：工具注册中心
- ✅ `builtin_tools.py`：内置工具实现
- ✅ `executor.py`：执行器（工具调用逻辑可参考）
- ✅ `memory.py`：记忆管理器
- ✅ `context.py`：上下文管理器

## 🎓 未来改进方向

### 短期（2.0.x）

1. **多任务支持**：支持多个任务并行执行
2. **任务队列**：异步任务调度和优先级管理
3. **结果缓存**：缓存相似任务的解决方案
4. **工具扩展**：支持更多外部 MCP 服务器

### 中期（2.1.x）

1. **流式输出**：更好的流式处理和进度显示
2. **调试模式**：详细的执行日志和中间状态
3. **性能优化**：减少 LLM 调用次数，缓存常用响应
4. **可视化**：ReAct 循环可视化界面

### 长期（3.0+）

1. **多模态支持**：同时支持 CLI、Web UI 和 IDE 插件
2. **协作功能**：多用户共享和协作编辑
3. **自动化流水线**：完整的 CI/CD 流程
4. **AI 模型切换**：支持更多 LLM 提供商（Claude、Gemini、Llama）

## 📝 总结

ReAct 循环架构为 IntelliAgent 2.0 带来了：

- ✅ 更简单、更直接的执行流程
- ✅ 更快速的用户响应
- ✅ 更适合代码开发场景
- ✅ 更好的实时交互体验
- ✅ 更灵活的错误处理和恢复机制
- ✅ 更完整的 Web UI 支持

通过移除复杂的 PDCA 循环，系统变得更加：
- **易理解**：Reason → Act → Observe 流程清晰
- **易维护**：组件职责明确，代码简洁
- **易扩展**：添加新功能更加直接
- **易测试**：每个组件可独立测试

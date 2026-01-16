# 🤖 IntelliAgent - 基于 PDCA 循环的智能代理系统

> 一个使用 OpenAI LLM 驱动的智能任务规划与执行系统，遵循 PDCA（Plan-Do-Check-Act）戴明环理论

## ✨ 核心特性

- **🎯 智能规划**: 使用 LLM 根据用户输入自动生成结构化执行计划
- **⚙️ 自动执行**: 调用工具执行计划中的各个步骤
- **🔍 质量检查**: LLM 评估每个步骤的执行质量，确保符合预期
- **🔄 自适应改进**: 失败时自动重试（最多3次），超出后智能调整计划
- **🧠 经验学习**: 保存成功和失败的经验，支持历史查询和学习

## 🏗️ 系统架构

基于 **PDCA 循环**设计：

```
┌─────────────────────────────────────────────────┐
│                  PDCA 循环                       │
│                                                 │
│  ┌──────┐   ┌──────┐   ┌──────┐   ┌──────┐   │
│  │ Plan │──▶│  Do  │──▶│Check │──▶│ Act  │   │
│  └──────┘   └──────┘   └──────┘   └──────┘   │
│      ▲                                  │       │
│      └──────────────────────────────────┘       │
│                 (循环重试/调整)                   │
└─────────────────────────────────────────────────┘
```

### 各阶段说明

| 阶段 | 模块 | 功能 |
|------|------|------|
| **Plan** | `planner.py` | 使用 LLM 生成执行计划，分解任务步骤 |
| **Do** | `executor.py` | 执行计划中的各个步骤，调用工具 |
| **Check** | `checker.py` | LLM 检查执行结果质量，评估是否达标 |
| **Act** | `actor.py` | 根据检查结果决定重试/调整计划/保存经验 |

### 核心模块

```
core/
├── llm_client.py      # OpenAI LLM 客户端封装
├── planner.py         # 规划器 (Plan)
├── executor.py        # 执行器 (Do)
├── checker.py         # 检查器 (Check)
├── actor.py           # 改进器 (Act)
├── pdca_loop.py       # PDCA 循环控制器
├── memory.py          # 记忆管理（支持经验保存）
├── context.py         # 上下文管理
└── tool_registry.py   # 工具注册中心
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制 `.env.example` 并重命名为 `.env`，填入你的 OpenAI API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL=gpt-4o-mini
MAX_PDCA_CYCLES=3
MAX_RETRY_PER_STEP=3

# 可选：配置外部 MCP 服务器（JSON 文件）
MCP_CONFIG_FILE=mcp_config.json
```

**关于工具系统**:
- 内置工具（6 个）无需配置，详见 [工具文档](docs/TOOLS.md)
- 外部 MCP 服务器通过 `mcp_config.json` 配置，详见 [集成指南](docs/TOOL_INTEGRATION.md)
- 使用与 Claude Code 兼容的 JSON 配置格式

### 3. 运行示例

#### 方式一：命令行直接运行

```bash
python main.py "创建一个 Python 文件并写入 Hello World"
```

#### 方式二：运行交互式示例（如存在 example.py）

```bash
python example.py
```

如果仓库包含该示例文件，可选择示例：
- 1. 简单文件操作
- 2. 复杂代码生成
- 3. Git 操作
- 4. 查看历史经验
- 5. 自定义配置

#### 方式三：在代码中使用

```python
from main import IntelliAgent

# 创建智能代理
agent = IntelliAgent()

# 执行任务
result = agent.run("列出当前目录文件")

# 查看结果
print(f"执行状态: {result['success']}")
print(f"摘要: {result['summary']}")

# 查看历史经验
experiences = agent.get_experiences()
```

## 🛠️ Tools - 工具系统

IntelliAgent 提供强大的工具系统，包括**内置工具**和**可扩展的外部工具**。

### 内置工具 (6 个)

开箱即用的基础工具，无需额外配置：

| 工具名 | 功能 | 参数 |
|-------|------|------|
| `run_shell` | 执行终端命令 | cmd: 命令字符串 |
| `read_file` | 读取文件内容 | path: 文件路径 |
| `write_file` | 写入文件内容 | path, content |
| `list_dir` | 列出目录内容 | path: 目录路径 |
| `delete_file` | 删除文件 | path: 文件路径 |
| `file_exists` | 检查文件是否存在 | path: 文件路径 |

### 外部工具 (可配置)

通过 MCP 协议集成第三方服务（如 GitHub、搜索、文档查询等）。

**已支持的外部服务**:
- `filesystem` - 高级文件操作
- `github` - GitHub API 集成
- `brave-search` - 互联网搜索
- `context7` - 编程文档查询
- `sequential-thinking` - 结构化思维

### 📖 完整文档

- **[快速入门指南](docs/QUICK_START.md)** - 工具系统使用快速入门（推荐首先阅读）
- **[工具系统文档](docs/TOOLS.md)** - 内置工具详细说明和使用示例
- **[MCP 集成指南](docs/TOOL_INTEGRATION.md)** - 如何配置和使用外部工具

### 📚 示例代码

- **[example.py](example.py)** - 交互式示例，展示 6 个工具的实际使用场景

## 🔧 配置说明

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | 必填 |
| `OPENAI_MODEL` | 使用的模型 | `gpt-4o-mini` |
| `MAX_PDCA_CYCLES` | 最大 PDCA 循环次数 | `3` |
| `MAX_RETRY_PER_STEP` | 单步骤最大重试次数 | `3` |
| `EXPERIENCE_FILE` | 经验保存文件路径 | `experiences.json` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

### 自定义配置

```python
agent = IntelliAgent(
    api_key="your-key",
    model="gpt-4o",        # 使用更强大的模型
    max_cycles=5,          # 允许更多循环
    max_retry=5            # 允许更多重试
)
```

## 🧠 经验学习机制

系统会自动保存每次任务执行的经验到 `experiences.json`：

```json
{
  "task": "创建Python文件",
  "plan": [...],
  "execution_results": [...],
  "check_results": [...],
  "final_status": "success",
  "total_steps": 3,
  "passed_steps": 3,
  "average_score": 0.95,
  "timestamp": "2025-11-13T10:30:00"
}
```

可以查询历史经验：

```python
# 查找相似任务的经验
similar = agent.get_experiences(task="创建文件", top_k=3)

# 查看所有经验
all_exp = agent.memory.get_all_experiences()
```

## 📊 执行流程示例

```
🚀 开始 PDCA 循环 | 任务: 创建一个 Python 文件
============================================================

📍 PDCA 循环第 1/3 轮
============================================================

📝 [PLAN] 生成执行计划...
✅ 计划生成完成 | 共 2 个步骤
   步骤 1: 创建文件目录
   步骤 2: 写入文件内容

⚙️  [DO] 执行计划...
➡️ 执行步骤 1: 创建文件目录
🧩 调用工具: run_shell 参数: {'cmd': 'mkdir -p test'}
✅ 工具执行成功
➡️ 执行步骤 2: 写入文件内容
🧩 调用工具: write_file 参数: {'path': 'test/hello.py', 'content': '...'}
✅ 工具执行成功
✅ 执行完成 | 完成 2 个步骤

🔍 [CHECK] 检查执行结果...
   ✅ 步骤 1: 通过 (得分: 1.00)
   ✅ 步骤 2: 通过 (得分: 0.95)
📊 整体检查: 完成 2/2 个步骤，平均得分 0.98

🎯 [ACT] 决策改进行动...
🎉 所有步骤执行成功！任务完成！

============================================================
📊 执行结果摘要
============================================================
状态: ✅ 成功
PDCA 循环次数: 1
总步骤数: 2
摘要: 任务成功完成，经过 1 轮 PDCA 循环
============================================================
```

## 🔬 工作原理

### 重试机制

当步骤执行失败时：
1. **第1-3次失败**: 自动重试相同步骤
2. **超过3次失败**: 调用 LLM 调整执行计划，开始新的 PDCA 循环
3. **最多3轮循环**: 防止无限循环

### 质量检查

LLM 会根据以下内容评估质量：
- 任务目标
- 预期结果
- 实际执行结果
- 上下文信息

返回评分（0-1）和通过/失败判定。

## 🛠️ 扩展开发

### 添加新工具

在 `mcp_server.py` 中添加新工具：

```python
@mcp.tool()
async def your_tool(param: str) -> str:
    """工具描述"""
    # 实现逻辑
    return success_response({"result": "..."})
```

### 自定义 LLM 提示词

修改 `llm_client.py` 中的 system_prompt 来调整 LLM 行为。

## 📚 文档

- 📖 [工具系统文档](docs/TOOLS.md) - 所有内置工具的详细说明
- 🔗 [MCP 集成指南](docs/TOOL_INTEGRATION.md) - 如何配置外部工具
- 🏗️ [架构设计文档](docs/ARCHITECTURE.md) - 深入了解系统设计原理（如存在）

## 📝 开发计划

- [ ] 支持更多 LLM 提供商（Claude, Gemini等）
- [ ] 添加向量数据库支持经验相似度搜索
- [ ] Web UI 界面
- [ ] 并行执行多个独立步骤
- [ ] 支持更复杂的工作流编排

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 支持

如果你遇到问题或有建议，请：
1. 查看 [快速开始指南](docs/QUICK_START.md) 的故障排除部分
2. 查看 [架构文档](docs/ARCHITECTURE.md) 了解系统工作原理
3. 提交 Issue 描述你的问题

---

**注意**: 请确保在 `.env` 中配置有效的 OpenAI API Key 才能正常使用。

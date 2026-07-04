# IntelliAgent

基于 ReAct 循环的代码开发助手框架。受 Claude Code、Codex、OpenCode 启发，强调**可解释性**、**模块清晰**和**架构即产出**。

## 架构

```
src/
├── cli/          CLI 界面（参数解析 + 输出格式化）
├── config/       统一配置（intelliagent.json + {env:VAR} 插值）
├── core/         ReAct 引擎核心循环
├── db/           持久化（SQLAlchemy ORM）
├── llm/          LLM 客户端适配器
├── mcp/          MCP 服务器管理
├── permission/   权限引擎（fnmatch + last-match-wins）
├── runtime/      运行时组装（AgentRuntime）
├── skills/       Skill 加载/注册/工具
├── tools/        工具注册表 + 内置工具
├── types/        类型定义
└── utils/        工具函数
```

**核心数据流**：`CLI → ConversationOrchestrator → AgentRuntime → ReactEngine → LLMClient → ToolRegistry`

## 快速开始

```bash
# 安装依赖
uv sync

# 配置
cp intelliagent.json.example intelliagent.json
# 编辑 intelliagent.json，设置 OPENAI_API_KEY

# 启动交互式对话
uv run python -m src.main

# 继续上一次对话
uv run python -m src.main --resume

# 查看历史对话
uv run python -m src.main --history
```

## 配置

所有配置收敛到单一 `intelliagent.json`，支持 `{env:VAR_NAME}` 环境变量插值：

```json
{
  "provider": {
    "openai": {
      "options": {
        "apiKey": "{env:OPENAI_API_KEY}",
        "baseURL": "{env:OPENAI_API_BASE}"
      }
    }
  },
  "permissions": {
    "rules": [
      { "pattern": "read *", "action": "allow" },
      { "pattern": "bash *", "action": "ask" }
    ]
  },
  "agent_team": {
    "enabled": false
  }
}
```

配置优先级：**环境变量 > intelliagent.json > 代码默认值**

## 核心内置工具

| 工具 | 说明 |
|------|------|
| `read_file` / `write_file` / `edit_file` | 文件操作 |
| `run_shell` | 命令执行 |
| `task_write` / `task_add` / `task_update` / `task_finish` | 任务管理（持久化到 SQLite） |
| `skill` | 按需加载 Skill 指令 |

## 可选 Agent Team 工具

Agent Team 默认关闭。需要多 Agent 通信与团队管理时，在 `intelliagent.json` 中设置：

```json
{
  "agent_team": { "enabled": true }
}
```

关闭时不会向模型注册 Agent Team 工具；相关数据库表仍随主 schema 创建。

启用后注册以下工具：

| 工具 | 说明 |
|------|------|
| `send_message` / `receive_message` / `get_contacts` / `get_contact_detail` / `create_agent` / `delete_agent` | Agent 间通信与团队管理 |

## CLI 命令

| 命令 | 说明 |
|------|------|
| `/exit` | 退出对话 |
| `/help` | 显示帮助 |

## 模块职责

| 模块 | 职责 |
|------|------|
| `src/core/` | ReAct 引擎、安全规则。不含 provider 逻辑和持久化。 |
| `src/llm/` | LLM 客户端适配器。不含 agent 循环策略。 |
| `src/tools/` | 工具实现 + 注册表。不含运行时组装。 |
| `src/runtime/` | 组合根：连接配置、LLM、权限、引擎。 |
| `src/db/` | 对话、消息、运行、追踪的持久化。 |
| `src/config/` | 类型化配置模型。 |

## License

MIT

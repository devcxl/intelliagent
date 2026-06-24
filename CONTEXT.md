# IntelliAgent Context Map

## 项目定位

IntelliAgent 是一个**编码 Agent 框架**（非 Web 应用），核心目标不是功能完备，而是**可解释的架构**——每个模块的职责用一句话能讲清楚，适合教学与展示。

## 架构分层

```
src/config/    类型化配置，无业务逻辑
src/core/      ReAct 引擎 + 安全规则，无 provider 和持久化
src/llm/       LLM 适配器，无 agent 循环策略
src/tools/     工具实现 + 注册表，无运行时组装
src/runtime/   组合根，组装所有依赖
src/db/        持久化层
src/permission/ 独立权限包
src/skills/    技能加载与注册
src/mcp/       MCP 服务器管理
```

## 核心概念

| 术语 | 定义 |
|------|------|
| **Run** | 一次完整的 agent 执行会话 |
| **Conversation** | 多轮对话，包含多条 Message |
| **Trace** | 一次 Run 中的工具调用追踪 |
| **Tool** | 可被 LLM 调用的能力单元，有 schema + 权限检查 |
| **Observation** | 工具执行结果的记录 |
| **Permission** | 工具调用的权限检查，fnmatch + last-match-wins |
| **Runtime** | 运行时组合根，组装 LLM/权限/引擎 |
| **Engine** | ReAct 循环核心，驱动 agent 推理-行动循环 |
| **Skill** | 按需加载的专家指令集，YAML frontmatter + Markdown 正文 |
| **MCP** | Model Context Protocol，外部工具服务器 |

## 设计原则

- **KISS/YAGNI**：不做过度设计，不写用不到的代码
- **模块边界清晰**：每层只做一件事，依赖通过构造函数注入
- **显式数据流**：避免全局状态，运行时组装创建具体对象
- **测试优先**：通过 monkeypatch 注入 fake 实现，各层独立测试
- **最小抽象**：不引入框架层，除非提供实质性杠杆

## 技术栈

- Python 3.11+, openai, pydantic, sqlalchemy, aiosqlite, mcp, pytest
- 依赖管理：uv
- 代码风格：ruff (line-length=120, double quotes)

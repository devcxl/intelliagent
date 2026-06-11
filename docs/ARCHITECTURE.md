# IntelliAgent 架构文档

> 生成日期：2026-06-11 | 分支：loop

---

## 一、项目概览

IntelliAgent 是一个基于 **ReAct 循环** 的智能代码开发助手，支持 CLI 和 Web UI 两种交互方式。LLM 自主决策调用工具（Shell、文件操作等），通过 Thought -> Action -> Observation 循环完成任务。

**技术栈**：Python 3.14 / FastAPI / SQLAlchemy / Alembic / OpenAI API / MCP 协议
**前端**：React 19 + TypeScript + Vite + Tailwind CSS
**数据库**：SQLite（开发阶段）

---

## 二、分层架构

```
入口层
  main.py (兼容)  ->  src/cli/main.py  ->  run / web 子命令
  src/app.py      ->  src/web/server.py (FastAPI)

API 层
  src/api/v1/  -- REST + WebSocket 路由
  conversations / runs / ws_runs

服务层
  src/services/run_service.py     -- 任务执行 + 持久化
  src/services/session_service.py -- 会话管理薄封装

运行时层
  src/runtime/agent_runtime.py  -- 共享工厂 + 单例
  LLM 客户端缓存 / 引擎创建 / 工具注册 / Memory / Context

引擎层
  src/agent/react_engine.py  -- ReAct 循环引擎
  src/llm/llm_client.py      -- LLM 客户端
  src/tools/tool_registry.py -- 工具注册中心
  src/tools/builtin_tools.py -- 7 个内置工具
  src/memory/memory.py       -- 记忆管理
  src/memory/context.py      -- 上下文管理

数据层
  src/db/  -- SQLAlchemy ORM + Repository 模式
  src/web/database.py -- 旧兼容适配器（过渡中）
  alembic/ -- 数据库迁移

配置层
  src/config/settings.py -- Pydantic Settings 统一配置
  utils/config.py -- 兼容层，委托至 Settings
```

---

## 三、核心模块详解

### 3.1 配置层 `src/config/settings.py`

- **类**：`Settings(BaseSettings)` -- Pydantic Settings，从 `.env` 加载
- **导出**：`get_settings()` (lru_cache 单例)
- **关键字段**：
  - `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_API_BASE`
  - `MAX_PDCA_CYCLES` (默认 3，实际用作 max_iterations)
  - `WEB_HOST` / `WEB_PORT` / `WEB_ENV`
  - `DATABASE_URL` (默认 `sqlite:///intelliagent.db`)
- **被引用**：runtime, web/server, web/database, utils/config, alembic

### 3.2 LLM 客户端 `src/llm/llm_client.py`

- **类**：`LLMClient`
- **核心方法**：
  - `chat()` / `chat_async()` -- 基础 OpenAI Chat
  - `generate_react_thought()` / `generate_react_thought_async()` -- ReAct 思考生成
  - `generate_plan()` / `check_result()` / `adjust_plan()` -- PDCA 遗留方法
- **依赖**：openai
- **被引用**：runtime（通过 AgentRuntime 工厂创建）

### 3.3 工具系统 `src/tools/`

| 文件 | 职责 |
|------|------|
| `builtin_tools.py` | 7 个内置工具：`run_shell`, `read_file`, `write_file`, `edit_file`, `list_dir`, `delete_file`, `file_exists` |
| `tool_registry.py` | `ToolRegistry`：统一管理内置工具 + MCP 外部工具（stdio/SSE/streamable-http） |

- 所有内置工具为 async 函数，返回 JSON 字符串
- MCP 外部工具通过 `mcp` 包加载，支持三种传输协议
- `ToolRegistry.call_tool_async()` 为统一调用入口

### 3.4 记忆系统 `src/memory/`

| 文件 | 职责 |
|------|------|
| `memory.py` | `Memory`：观察记录（内存列表）+ 经验持久化（JSON 文件） |
| `context.py` | `ContextManager`：简单字符串历史（最多 10 条） |

- 两者职责有重叠，ContextManager 功能极简
- Memory 支持 `save_experience()` / `get_similar_experiences()`（基于关键词匹配）

### 3.5 ReAct 引擎 `src/agent/react_engine.py`

- **类**：`ReactEngine`
- **核心流程**：`iter_steps()` 异步生成器，产生事件流
- **事件类型**：`thought` -> `action` -> `observation` -> `answer` / `error` / `cancelled` / `timeout`
- **关键方法**：
  - `run_async()` -- 完整执行，返回结果字典
  - `iter_steps()` -- 异步生成器，逐事件产出
  - `_generate_thought_async()` -- 调用 LLM 生成思考
  - `_execute_and_observe_async()` -- 执行工具并记录结果
- **支持特性**：取消检查、种子观察、迭代恢复、重置状态控制
- **依赖注入**：llm_client, tools, memory, context 全部通过构造函数注入

### 3.6 运行时 `src/runtime/agent_runtime.py`

- **类**：`AgentRuntime`（通过 `get_runtime()` 获取单例）
- **职责**：共享重对象管理 + 任务级工厂
  - LLM 客户端缓存（按 api_key/model 区分）
  - `create_engine()` -- 创建任务级 ReactEngine
  - `create_tool_registry()` / `create_memory()` / `create_context()`
  - `warm_up()` -- 预热共享资源

### 3.7 服务层 `src/services/`

| 文件 | 职责 |
|------|------|
| `run_service.py` | `RunService`：统一 CLI/Web 任务执行入口，含持久化、取消、重跑、恢复 |
| `session_service.py` | `SessionService`：对 DatabaseManager 的薄封装 |

**RunService 核心流程**：
1. 创建 Run 记录（pending -> running）
2. 调用 `ReactEngine.iter_steps()` 执行任务
3. 每个事件通过 `_persist_event()` 写入 ExecutionTrace
4. 终端事件通过 `_finish_run()` 更新 Run 状态，写入 Message
5. 支持 `cancel_run()` / `rerun()` / `resume()`

### 3.8 数据层 `src/db/`

**ORM 模型**（5 个）：

| 模型 | 表 | 关键字段 |
|------|-----|---------|
| `User` | users | id, username, display_name, created_at |
| `Conversation` | conversations | id, user_id(FK), title, task, status |
| `Run` | runs | id, conversation_id(FK), status, max_iterations, current_iteration, cancel_requested, source_run_id |
| `Message` | messages | id, conversation_id(FK), role, content |
| `ExecutionTrace` | execution_traces | id, run_id(FK), iteration, type, data(JSON) |

**关系**：User 1:N Conversation, Conversation 1:N Run, Conversation 1:N Message, Run 1:N ExecutionTrace

**约束**：`runs` 表有部分唯一索引，确保每个 conversation 只有一个活跃 run

**Repository 模式**：每个模型对应一个 Repository 类，封装 CRUD + 业务查询

**DatabaseSessionManager**：管理 SQLAlchemy async engine + session factory

### 3.9 Web 层

#### `src/web/server.py` -- FastAPI 应用

- **端点**：
  - REST：`/api/run`, `/api/sessions/*`, `/api/runs/*`
  - WebSocket：`/ws/run`
  - v1 API：通过 `app.include_router()` 挂载 conversations/runs/ws_runs 路由
- **生命周期**：`lifespan` 中初始化 DatabaseManager, SessionService, RunService
- **静态文件**：支持多级路径回退的生产/开发模式

#### `src/web/database.py` -- 兼容适配器

- **类**：`DatabaseManager`
- **状态**：过渡层，内部委托给新的 ORM Repository
- **问题**：`append_log()` 已弃用

#### `src/api/v1/` -- API 路由

| 路由 | 端点 |
|------|------|
| `conversations.py` | `GET /api/v1/conversations`, `GET /{id}`, `GET /{id}/messages`, `GET /{id}/runs` |
| `runs.py` | `POST /api/v1/runs`, `GET /{run_id}`, `GET /{run_id}/traces`, `POST /{run_id}/cancel`, `POST /rerun`, `POST /{run_id}/resume` |
| `ws_runs.py` | `WS /api/v1/ws/runs` |

### 3.10 CLI 入口 `src/cli/main.py`

- **类**：`IntelliAgent`
- **子命令**：`run`（执行任务）、`web`（启动 Web 服务器）
- **兼容**：`normalize_legacy_argv()` 处理旧格式参数

### 3.11 前端 `frontend/`

- **技术栈**：React 19 + TypeScript + Vite + Tailwind CSS + Radix UI
- **通信方式**：WebSocket（实时日志推送）+ REST API（会话管理）
- **组件树**：
  - App -> ThemeProvider -> Sidebar（会话列表）/ LogViewer（日志展示）/ InputArea（任务输入）
  - ThemeToggle（主题切换）
- **Vite 代理**：`/ws` 和 `/api` 代理到 `localhost:8000`

---

## 四、数据流

```
用户输入 (CLI/Web/WebSocket)
    |
    v
IntelliAgent / FastAPI endpoint
    |
    v
RunService.run_task_async() / run_task_stream()
    |
    +-- 有 conversation_id -> _run_persisted_task()
    |   +-- 创建 Run 记录 (pending -> running)
    |   +-- 调用 ReactEngine.iter_steps()
    |   +-- 每个事件 -> _persist_event() -> ExecutionTrace
    |   +-- 终端事件 -> _finish_run() -> 更新 Run + 写入 Message
    |
    +-- 无 conversation_id -> ReactEngine.run_async()（无持久化）
        |
        v
    ReactEngine.iter_steps() [异步生成器]
        |
        +-- _generate_thought_async()
        |   +-- LLMClient.generate_react_thought_async()
        |       +-- OpenAI API
        |
        +-- [thought] -> yield
        +-- [action]  -> yield
        +-- _execute_and_observe_async()
        |   +-- ToolRegistry.call_tool_async()
        |       +-- 内置工具（直接调用）
        |       +-- MCP 外部工具（通过协议）
        |
        +-- [observation] -> yield -> Memory.add_observation()
        +-- [answer/error/cancelled/timeout] -> yield -> 终止
```

---

## 五、入口点

| 入口 | 文件 | 命令 |
|------|------|------|
| CLI | `src/cli/main.py` | `intelliagent run "任务"` 或 `python main.py "任务"` |
| Web | `src/web/server.py` | `intelliagent web` 或 `uvicorn src.app:app` |
| 兼容 | `main.py` | `python main.py`（委托给 CLI） |

---

## 六、已知架构问题

### 严重

#### 1. `src/agent/executor.py` -- 死代码（681 行）

旧 PDCA 架构的 "Do" 阶段执行引擎，包含重试/退避/依赖检查/恢复策略/执行指标等高级特性。**未被任何模块 import**，项目已全面迁移到 ReAct。

**建议**：删除，或将其重试/恢复机制迁移到 ReactEngine。

#### 2. 两套并行 Skill 系统 -- 均未集成

| | 系统 A（旧） | 系统 B（新） |
|---|---|---|
| 文件 | `skill.py` + `skill_manager.py` | `skill_system.py` + `skill_loader.py` |
| Skill 类 | `CodeSkill`（Python exec 执行） | `Skill`（Markdown 文档解析） |
| 存储 | `skills/*.json` | `.claude/skills/*/SKILL.md` |
| 测试 | 已禁用（`.disabled`） | 活跃但无实际 Skill 数据 |

- 两套系统互不兼容，零交叉引用
- `ReactEngine` 和 `AgentRuntime` 均未导入任何 skills 模块
- `skill_integration.py` 的 `SkillExecutor.execute()` 存在 Bug：调用 `skill.execute()` 但系统 B 的 `Skill` 类没有该方法
- 仓库中不存在任何实际的 Skill 定义文件

**建议**：选定一套方案，完成集成或删除。

#### 3. Skills 未集成到 ReAct 循环

`LLMClient.generate_react_thought()` 接受 `skills_context` 参数，但 `ReactEngine._generate_thought_async()` 从不传入。Skill 系统完全独立于核心执行路径。

### 中等

#### 4. 两套数据库访问层并存

- `src/web/database.py`（DatabaseManager，旧兼容层）
- `src/db/`（新 ORM + Repository）

`SessionService` 直接依赖 DatabaseManager 而非 Repository。DatabaseManager 注释明确标记为"过渡"。

**建议**：完成迁移，删除 DatabaseManager。

#### 5. API 路由重复

`src/web/server.py` 直接定义了 `/api/sessions`, `/api/runs/cancel` 等端点，同时 `src/api/v1/` 也定义了 `/api/v1/conversations`, `/api/v1/runs` 等。两套路由体系并存。

**建议**：统一到 v1 路由，删除 server.py 中的旧端点。

#### 6. Memory 与 Context 职责重叠

`Memory`（观察记录 + 经验持久化）和 `ContextManager`（字符串历史）功能有重叠，ContextManager 仅保留 10 条记录，功能极简。

**建议**：合并或明确分工。

### 轻微

#### 7. 模块级全局变量

`src/web/server.py` 使用模块级全局变量 `db`, `session_service`, `run_service`，而非通过 FastAPI 的 `app.state` 或依赖注入管理。

#### 8. PDCA 命名残留

`MAX_PDCA_CYCLES` 配置项名称仍保留 PDCA 痕迹，实际已用作 ReAct 的 `max_iterations`。

#### 9. ToolRegistry 事件循环 hack

`get_tool()` 在已有运行中的事件循环时，使用 `threading.Thread` + 新事件循环的 hack 方式调用 MCP 工具。

---

## 七、模块依赖图

```
main.py --> src/cli/main.py --> src/runtime/agent_runtime.py
                                    |
src/app.py --> src/web/server.py ---+
                  |                  |
                  v                  v
          src/api/v1/*      src/agent/react_engine.py
                  |                  |
                  v                  +--> src/llm/llm_client.py
          src/services/              +--> src/tools/tool_registry.py
          +-- run_service.py --------|     +--> src/tools/builtin_tools.py
          +-- session_service.py     +--> src/memory/memory.py
                  |                  +--> src/memory/context.py
                  v
          src/web/database.py --> src/db/session.py
                                      +--> src/db/repositories/*
                                            +--> src/db/models/*

所有模块 --> utils/logger.py
所有模块 --> src/config/settings.py (通过 get_settings)
```

---

## 八、Skills 系统详细分析

### 系统 A：旧版 CodeSkill（`skill.py` + `skill_manager.py`）

- `CodeSkill` 类：通过 Python `exec()` 在受限沙箱中执行代码
- `SkillManager`：管理 `skills/` 目录下的 JSON 持久化
- 测试文件已禁用（`.disabled` 后缀）
- **Bug**：`get_stats()` 引用不存在的 `self.index["by_type"]`

### 系统 B：新版 Claude Code Skill（`skill_system.py` + `skill_loader.py`）

- `Skill` 类：从 `.claude/skills/{name}/SKILL.md` 加载 YAML + Markdown
- `SkillLoader`：扫描 `.claude/skills/` 目录，支持关键词相关度匹配
- `SkillIntegration`：桥接层，提供 LLM 友好的 Skill 描述
- **Bug**：`SkillExecutor.execute()` 调用 `skill.execute()` 但 `Skill` 类没有该方法
- 仓库中不存在 `.claude/skills/` 目录

### 结论

两套系统互不兼容，均未被 ReAct 引擎集成。`ReactEngine` 和 `AgentRuntime` 都没有导入任何 skills 模块。整个 `src/skills/` 目前是死代码。

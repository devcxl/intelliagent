# IntelliAgent 统一 CLI + Web 详细任务清单

> 本文从 `docs/plan.md` 拆解而来，目的是把蓝图转换为可执行任务清单。执行时如有冲突，以 `docs/plan.md` 为准。

---

## 1. 总体执行规则

- 主线顺序：`PR1 → PR2 → PR3 → PR4 → (PR5 与 PR6 可并行) → PR7`
- 每个阶段都必须收口到四类事项：**代码改动、测试补齐、文档更新、冒烟验证**
- 每个阶段最低验收标准：**单测 + 集成 + CLI 冒烟 + Web 冒烟**（按该阶段适用范围执行）
- 严格遵守以下边界：
  - 不让 CLI 和 Web 各自维护一套执行链
  - 不让 `main.py` 同时承担 CLI / Web / 核心装配三种职责
  - 不混存 `message` 与 `execution_trace`
  - 不跳过 Alembic
  - 不让认证成为本地匿名模式的前置条件

---

## 2. 第一阶段最小成型目标

在全部任务完成后，至少应满足：

- `intelliagent run "任务"` 可以执行
- `uvicorn src.app:app` 可以启动
- HTTP 可以创建会话和 run
- WebSocket 可以实时推送执行事件
- SQLite 默认可用
- 数据库中存在 `users / conversations / runs / messages / execution_traces`
- 支持 `cancel / rerun / resume`
- 满足“多会话可并发、单会话单活跃 run”约束

---

## 3. 任务拆解总览

| 阶段 | 核心目标 | 依赖 | 并行性 |
|---|---|---|---|
| PR1 | 统一入口、配置、目录边界 | 无 | 串行起点 |
| PR2 | 抽共享 runtime / service | PR1 | 串行 |
| PR3 | 建数据层与 Alembic 基线 | PR2 | 串行 |
| PR4 | 核心执行链异步化、落地 run 生命周期 | PR3 | 串行 |
| PR5 | 重做 CLI 子命令 | PR4 | 可与 PR6 并行 |
| PR6 | Web API / WS 统一到共享 service | PR4 | 可与 PR5 并行 |
| PR7 | 前端路由壳与对话主视图 | PR5 + PR6 | 最后执行 |

---

## 4. PR1：统一骨架与配置

### 目标

- 固定 CLI / Web 入口
- 配置统一到 Pydantic Settings
- 明确兼容入口与长期入口边界

### 详细任务

- [ ] **T1.1 盘点现状入口**
  - 梳理当前 CLI、Web、核心装配分别从哪些文件进入
  - 标出需要保留的兼容路径和必须废弃的长期路径
- [ ] **T1.2 统一配置模型**
  - 新建或收敛 `src/config/settings.py`
  - 统一环境变量读取、默认值、`.env` 加载和开发/测试配置来源
  - 明确 `DATABASE_URL`、模型配置、Web 启动配置等字段归属
- [ ] **T1.3 固定 Web 主入口**
  - 让 `src/app.py` 暴露稳定 `app` 对象
  - 清理 Web 启动所需的基础装配逻辑，避免继续依赖旧入口
- [ ] **T1.4 固定 CLI 主入口**
  - 让 `src/cli/main.py` 成为唯一长期 CLI 根入口
  - 先提供最小可用骨架：主解析器、根命令、帮助输出
- [ ] **T1.5 收敛 `main.py` 角色**
  - 将 `main.py` 降级为兼容入口或转发层
  - 删除其内部的核心装配职责，只保留薄封装
- [ ] **T1.6 更新包级启动契约**
  - 更新 `pyproject.toml` 中的 CLI entry point
  - 确保包命令为主、脚本方式兼容
- [ ] **T1.7 更新说明文档**
  - 更新 `README.md` 中的推荐启动方式、入口说明和过渡说明
  - 明确 `src/app.py` 与 `src/cli/main.py` 为目标入口
- [ ] **T1.8 补基础验证**
  - 增加配置加载、Web 入口导入、CLI 入口导入相关测试或冒烟脚本

### 产出物

- 稳定的 `src/app.py`
- 稳定的 `src/cli/main.py`
- 统一的 `src/config/settings.py`
- 降级为兼容入口的 `main.py`

### 验收命令

```bash
pytest
python -c "from src.app import app; print(app.title)"
python -c "from src.cli.main import main; print(callable(main))"
```

---

## 5. PR2：抽共享 runtime / service 层

### 目标

- CLI / Web 共用同一执行入口
- 停止在多个入口重复拼装核心对象

### 详细任务

- [ ] **T2.1 盘点核心装配点**
  - 找出当前 CLI、Web、脚本入口里直接 `new` 核心对象的位置
  - 标出可抽到共享层的重对象和必须按任务创建的轻对象
- [ ] **T2.2 设计 runtime 边界**
  - 新增 `src/runtime/agent_runtime.py`
  - 明确 runtime 负责共享重对象初始化，如 `LLMClient / ToolRegistry / SkillIntegration`
- [ ] **T2.3 设计 session service**
  - 新增 `src/services/session_service.py`
  - 统一会话创建、查询、续接、匿名默认用户相关能力入口
- [ ] **T2.4 设计 run service**
  - 新增 `src/services/run_service.py`
  - 统一 run 的启动、状态流转、事件分发、取消、重跑、续跑入口
- [ ] **T2.5 调整 `react_engine` 调用方式**
  - 保留 `ReactEngine` 作为任务级对象
  - 确保它由 runtime / service 间接创建，而不是由 CLI / Web 直接实例化
- [ ] **T2.6 替换旧入口装配逻辑**
  - CLI 改走 service
  - Web 改走 service
  - 兼容入口也只做转发，不再拼核心
- [ ] **T2.7 统一执行事件模型**
  - 为后续 CLI 输出、HTTP 响应、WebSocket 推送预留统一事件结构
  - 明确消息与执行痕迹的边界，不在 service 层混用
- [ ] **T2.8 补单测与最小集成验证**
  - 覆盖 runtime 初始化
  - 覆盖 session / run service 的最小调用链
  - 回归 `test_react_engine` 相关测试

### 产出物

- `src/runtime/agent_runtime.py`
- `src/services/session_service.py`
- `src/services/run_service.py`
- 去重后的核心装配路径

### 验收命令

```bash
pytest tests/unit/test_react_engine.py
python -c "from src.services.run_service import RunService; print(RunService)"
python -c "from src.runtime.agent_runtime import AgentRuntime; print(AgentRuntime)"
```

---

## 6. PR3：数据层 + Alembic 基线

### 目标

- 正式入库
- 建立 schema 与 migration 基线
- 消息与执行痕迹分离存储

### 详细任务

- [ ] **T3.1 统一数据库接入方式**
  - 在 settings 中固化 `DATABASE_URL`
  - 默认使用 SQLite，同时允许后续切 PostgreSQL / 其他数据库
- [ ] **T3.2 建立数据库会话管理**
  - 新增 `src/db/session.py`
  - 统一 engine、session factory、事务边界和测试态数据库接入方式
- [ ] **T3.3 设计核心表结构**
  - 定义 `users`、`conversations`、`runs`、`messages`、`execution_traces`
  - 明确主外键、时间字段、状态字段和必要索引
- [ ] **T3.4 明确 run 相关状态字段**
  - 为 run 生命周期预留状态枚举、取消标记、来源 run、恢复点等字段
  - 避免把生命周期语义塞进 message 或 trace
- [ ] **T3.5 设计匿名本地用户策略**
  - 落地默认匿名用户的数据表示
  - 保证无认证模式下 CLI / Web 都能写入同一库
- [ ] **T3.6 搭建 Alembic 基线**
  - 新增 `alembic.ini` 与 `alembic/`
  - 生成第一版 baseline migration
  - 统一后续 schema 变更路径
- [ ] **T3.7 建 repository 层**
  - 为 conversation、run、message、trace 提供清晰的读写接口
  - 避免 service 直接拼 ORM 细节
- [ ] **T3.8 补齐环境示例与初始化说明**
  - 更新 `.env.example`
  - 明确本地 SQLite、测试数据库、迁移命令用法
- [ ] **T3.9 增加 repository / migration 测试**
  - 覆盖 schema 创建
  - 覆盖基础 CRUD
  - 覆盖 message 与 trace 分离落库

### 产出物

- `alembic.ini`
- `alembic/` 目录与 baseline migration
- `src/db/session.py`
- `src/db/models/*`
- `src/db/repositories/*`
- `.env.example`

### 验收命令

```bash
alembic upgrade head
pytest tests/unit tests/integration
```

---

## 7. PR4：核心全面异步化 + run 生命周期

### 目标

- 核心执行链改为 async
- 落地并发、取消、续跑、重跑语义
- 让 run 生命周期具备可测试状态机

### 详细任务

- [ ] **T4.1 盘点同步链路**
  - 找出 `react_engine`、工具调用、service 调度中仍为同步的关键路径
  - 明确哪些方法必须升级为 async，哪些可做适配层
- [ ] **T4.2 异步化 `ReactEngine`**
  - 让核心推理 / 工具执行 / 结果产出走统一异步接口
  - 确保 CLI 最终通过 `asyncio.run(...)` 驱动
- [ ] **T4.3 异步化工具调用约定**
  - 调整 `src/tools/builtin_tools.py`
  - 调整 `src/tools/tool_registry.py`
  - 明确同步工具如何包装、异步工具如何注册和调度
- [ ] **T4.4 定义 run 状态机**
  - 明确 run 的状态枚举、状态迁移和非法迁移处理
  - 明确启动、执行中、完成、失败、取消、恢复中的系统行为
- [ ] **T4.5 实现单会话单活跃 run 约束**
  - 在 service / repository 层建立并发控制
  - 阻止同一会话下同时跑两个活跃 run
- [ ] **T4.6 实现协作式取消**
  - 提供取消信号、轮询检查点和安全退出逻辑
  - 确保取消不会破坏已落库历史
- [ ] **T4.7 实现 rerun / resume 语义**
  - `rerun`：从已有上下文创建新 run
  - `resume`：恢复旧 run 的继续执行
  - 明确两者的数据库字段和事件行为差异
- [ ] **T4.8 打通消息与痕迹写入链**
  - 用户可见内容走 `message`
  - 结构化过程走 `execution_trace`
  - 两类数据在异步执行时保持顺序一致性
- [ ] **T4.9 增加生命周期测试**
  - 覆盖正常完成
  - 覆盖取消
  - 覆盖同会话并发冲突
  - 覆盖 rerun / resume 差异

### 产出物

- 异步化后的 `react_engine`
- 支持生命周期语义的 `run_service`
- 统一的异步工具调用契约

### 验收命令

```bash
pytest tests/unit/test_react_engine.py
pytest tests/integration/test_run_lifecycle.py
```

---

## 8. PR5：新 CLI

### 目标

- CLI 改为子命令式
- 默认人类可读输出，同时支持 `--json`

### 详细任务

- [ ] **T5.1 设计 CLI 命令树**
  - 明确根命令、`run`、`conversation`、`history` 等子命令边界
  - 明确保留哪些兼容参数，废弃哪些旧风格参数
- [ ] **T5.2 实现 `run` 命令**
  - 支持默认新会话执行
  - 支持显式续接会话
  - 支持人类可读输出和 `--json`
- [ ] **T5.3 实现 `conversation` 命令**
  - 支持会话查询、查看、续接或相关管理动作
  - 命令参数与数据库语义对齐
- [ ] **T5.4 实现 `history` 命令**
  - 支持查看 run 历史、消息历史或执行记录摘要
  - 输出格式与后续脚本集成需求兼容
- [ ] **T5.5 统一 CLI 输出层**
  - 定义人类可读输出模板
  - 定义 `--json` 结构，避免把内部对象直接打印给用户
- [ ] **T5.6 让 CLI 全量走共享 service**
  - 所有命令都通过 runtime / service 调用
  - 禁止 CLI 旁路直接访问核心执行对象
- [ ] **T5.7 保留脚本兼容性**
  - 保证旧 `main.py` 或脚本方式仍可转发到新 CLI
  - 明确兼容范围和废弃提示
- [ ] **T5.8 增加 CLI 测试与冒烟用例**
  - 覆盖 `--help`
  - 覆盖 `run`
  - 覆盖 `run --json`
  - 覆盖会话续接基础链路

### 产出物

- `src/cli/commands/run.py`
- `src/cli/commands/conversation.py`
- `src/cli/commands/history.py`
- 新的 CLI 输出契约

### 验收命令

```bash
python -m src.cli.main --help
intelliagent run "测试任务"
intelliagent run "测试任务" --json
```

---

## 9. PR6：Web 外壳 + HTTP / WebSocket 双轨

### 目标

- Web 服务固定到 `src/app.py + src/api/v1/*`
- HTTP 与 WebSocket 共用同一 service
- 默认本地匿名可用，认证代码只做预留

### 详细任务

- [ ] **T6.1 固化 API 路由结构**
  - 在 `src/app.py` 注册 `src/api/v1/*` 路由
  - 明确版本前缀、健康检查、静态资源入口等基础结构
- [ ] **T6.2 建立 API 依赖注入层**
  - 新增 `src/api/deps.py`
  - 统一 settings、db session、service、用户上下文依赖获取方式
- [ ] **T6.3 实现会话 HTTP 接口**
  - 新增 `src/api/v1/sessions.py`
  - 支持创建会话、查询会话、获取会话详情等最小能力
- [ ] **T6.4 实现 run HTTP 接口**
  - 新增 `src/api/v1/runs.py`
  - 支持创建 run、取消 run、重跑、续跑等核心动作
- [ ] **T6.5 实现 WebSocket 事件流接口**
  - 新增 `src/api/v1/ws_runs.py`
  - 将 run 生命周期事件实时推送给前端
  - 明确订阅粒度、事件格式和断线重连后的补偿策略
- [ ] **T6.6 落地匿名默认用户机制**
  - Web 本地模式默认直达
  - 认证代码保留为可配置增强，但默认关闭
- [ ] **T6.7 清理旧 Web 主路径**
  - 废弃或删除 `src/web/server.py` 的主入口角色
  - 清理旧旁路装配逻辑
- [ ] **T6.8 增加 API / WS 测试**
  - 覆盖建会话、建 run、取消 run
  - 覆盖 WebSocket 实时收事件
  - 覆盖匿名模式可用性

### 产出物

- `src/app.py` 中的正式路由装配
- `src/api/v1/sessions.py`
- `src/api/v1/runs.py`
- `src/api/v1/ws_runs.py`
- `src/api/deps.py`

### 验收命令

```bash
uvicorn src.app:app --reload
```

### 手工验收

- HTTP：创建会话
- HTTP：创建 run
- HTTP：取消 run
- WebSocket：实时接收事件

---

## 10. PR7：前端路由壳 + 对话主视图

### 目标

- 前端切到路由壳结构
- 主视图以对话为中心，执行痕迹侧展
- 生产由后端托管前端静态文件

### 详细任务

- [ ] **T7.1 重构前端入口结构**
  - 改造 `frontend/src/App.tsx`
  - 引入路由壳与页面级布局
  - 为匿名默认直达主页预留路由逻辑
- [ ] **T7.2 建立主页面模型**
  - 新增或调整 `frontend/src/pages/MainPage.tsx`
  - 明确左侧会话 / 中间对话 / 侧边执行痕迹的布局关系
- [ ] **T7.3 建立路由与页面组织**
  - 新增 `frontend/src/routes/*`
  - 让会话切换、主视图展示和刷新恢复有稳定路由语义
- [ ] **T7.4 建立 API 访问层**
  - 在 `frontend/src/lib/*` 中统一封装会话、run、message、trace API
  - 不再让页面直接拼请求
- [ ] **T7.5 建立 WebSocket Hook**
  - 新增 `frontend/src/hooks/useWebSocket.ts`
  - 处理连接、重连、事件分发和页面状态同步
- [ ] **T7.6 分离消息与执行痕迹状态**
  - 消息来自 message API
  - 执行过程来自 trace API / WS
  - 前端不再把 `logs` 当唯一真相源
- [ ] **T7.7 打通运行操作**
  - 支持运行任务
  - 支持 cancel / rerun / resume
  - 支持刷新后回放消息与痕迹
- [ ] **T7.8 接入后端静态托管**
  - 调整打包输出和后端静态资源服务路径
  - 更新 `scripts/start-web*.sh`
- [ ] **T7.9 增加前端联调与构建验证**
  - 覆盖基础路由渲染
  - 覆盖任务执行链路
  - 覆盖刷新恢复

### 产出物

- `frontend/src/App.tsx`
- `frontend/src/routes/*`
- `frontend/src/pages/MainPage.tsx`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/lib/*`
- `scripts/start-web*.sh`

### 验收命令

```bash
cd frontend && npm run build
uvicorn src.app:app
```

### 手工验收

- 新建会话
- 运行任务
- `cancel / rerun / resume`
- 刷新后回放消息与痕迹

---

## 11. 横切任务清单

下面这些事情不是单独一个 PR 的目标，但每个阶段都要检查：

- [ ] **X1 测试补齐**
  - 单测补核心语义
  - 集成测补跨层链路
  - CLI / Web 冒烟命令纳入回归
- [ ] **X2 文档同步**
  - README、快速开始、目录结构、验证文档与当前阶段保持一致
  - 历史文档要明确标记，不误导为当前标准
- [ ] **X3 兼容路径管理**
  - 所有兼容入口、兼容脚本、废弃路径都要写清楚去留时间点
- [ ] **X4 事件与数据契约统一**
  - CLI 输出、HTTP 响应、WebSocket 事件、DB schema 命名尽量统一
- [ ] **X5 匿名模式验证**
  - 每个 Web 相关阶段都要确认“默认本地匿名可用”没有被破坏
- [ ] **X6 生命周期语义一致性**
  - `run / cancel / rerun / resume` 在 CLI、HTTP、WebSocket、数据库四处语义一致

---

## 12. 建议执行顺序

### 阶段 A：先打骨架

1. 完成 PR1
2. 完成 PR2
3. 完成 PR3
4. 完成 PR4

### 阶段 B：入口并行收敛

5. PR5 与 PR6 并行推进
6. 对齐 CLI / API / WS 的统一 service 契约

### 阶段 C：最后闭环前端

7. 完成 PR7
8. 做端到端联调和生产托管验证

---

## 13. 最终验收清单

- [ ] `intelliagent run "任务"` 可执行
- [ ] `intelliagent run "任务" --json` 输出结构稳定
- [ ] `uvicorn src.app:app` 可启动
- [ ] HTTP 可创建会话
- [ ] HTTP 可创建 / 取消 / 重跑 / 续跑 run
- [ ] WebSocket 可持续接收执行事件
- [ ] 默认 SQLite 可用
- [ ] CLI 与 Web 写入同一数据库
- [ ] `users / conversations / runs / messages / execution_traces` 表结构稳定
- [ ] 消息与执行痕迹分离存储
- [ ] 多会话可并发
- [ ] 单会话单活跃 run
- [ ] 匿名模式默认可用
- [ ] 前端刷新后可回放消息与痕迹

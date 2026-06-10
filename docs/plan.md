# IntelliAgent 统一 CLI + Web 实施蓝图

## 结论

目标架构：

- 对外统一入口，内部共享核心
- CLI 与 Web 共用一套执行链路
- 核心执行链全面异步化
- Web 默认本地匿名可用，认证作为可选增强
- CLI 与 Web 都统一入库
- 数据库通过 `DATABASE_URL` 可插拔，默认 SQLite

主线顺序：

`PR1 → PR2 → PR3 → PR4 → (PR5 与 PR6 可并行) → PR7`

---

## 已确认的关键决策

1. 对外统一入口，内部共享核心
2. 核心全面异步，CLI 用 `asyncio.run(...)`
3. 配置统一到 Pydantic Settings
4. Web 外壳采用 `src/app.py + src/api/v1/*`
5. 共享重对象，`Memory/Context/ReactEngine` 按任务创建
6. Web 默认本地匿名可用，认证可选增强
7. CLI 和 Web 都统一入库
8. `DATABASE_URL` 可插拔，默认 SQLite
9. 首版沿用完整聊天模型
10. CLI 默认新会话，可选续接
11. 消息与结构化执行痕迹分离存储
12. 匿名模式采用内置本地用户
13. 认证代码预留，默认关闭
14. 前端采用路由壳，匿名模式默认直达主页
15. 执行接口采用 HTTP + WebSocket 双轨
16. 通过薄的 runtime/service 层共享执行能力
17. Schema 从第一版就走 Alembic migration
18. 允许重做 CLI
19. CLI 采用子命令式
20. CLI 默认人类可读，支持 `--json`
21. Web 主视图以对话为主，执行痕迹侧展
22. 多会话可并发，单会话单活跃 run
23. 取消采用协作式取消
24. 重跑新 run，续跑旧 run
25. 第一阶段按端到端竖切片推进
26. 每个切片最低验收：单测 + 集成 + CLI/Web 冒烟
27. CLI 启动契约：包命令为主，脚本兼容
28. Migration 工具：Alembic
29. 生产由后端托管前端静态文件

---

## 最小竖切片

做到下面这条链路，第一阶段就算成型：

- `intelliagent run "任务"` 能执行
- `uvicorn src.app:app` 能启动
- HTTP 能创建会话和 run
- WebSocket 能实时推送执行事件
- SQLite 默认可用
- 数据库内有 `users / conversations / runs / messages / execution_traces`
- 支持：单会话单活跃 run、cancel、rerun、resume

---

## 实施步骤

## PR1：统一骨架与配置

### 目标

- 固定入口和目录边界
- 配置统一到 Pydantic Settings

### 主要改动目录/文件

- `pyproject.toml`
- `src/app.py`
- `src/cli/main.py`
- `src/config/settings.py`
- `main.py`（降为兼容入口）
- `README.md`

### 关键设计约束

- 不再让 `main.py` 同时承担 CLI/Web/核心装配
- Web 主入口固定为 `src/app.py`

### 验证

```bash
pytest
python -c "from src.app import app; print(app.title)"
python -c "from src.cli.main import main; print(callable(main))"
```

### 完成定义

- 有包级 CLI 入口
- 有统一 `settings`
- 有明确 CLI/Web 入口路径

---

## PR2：抽共享 runtime/service 层

### 目标

- CLI / Web 共用同一执行入口
- 停止各处自己拼引擎

### 主要改动目录/文件

- `src/runtime/agent_runtime.py`
- `src/services/run_service.py`
- `src/services/session_service.py`
- `src/agent/react_engine.py`
- `main.py`

### 关键设计约束

- 共享：`LLMClient / ToolRegistry / SkillIntegration`
- 按任务新建：`Memory / Context / ReactEngine`

### 验证

```bash
pytest tests/unit/test_react_engine.py
python -c "from src.services.run_service import RunService; print(RunService)"
python -c "from src.runtime.agent_runtime import AgentRuntime; print(AgentRuntime)"
```

### 完成定义

- CLI 和 Web 都不再直接 new 全套核心对象

---

## PR3：数据层 + Alembic 基线

### 目标

- 正式入库
- 建立 migration 基线
- 消息与执行痕迹分离

### 主要改动目录/文件

- `alembic.ini`
- `alembic/`
- `src/db/session.py`
- `src/db/models/*`
- `src/db/repositories/*`
- `.env.example`

### 关键设计约束

- `DATABASE_URL` 可插拔，默认 SQLite
- 首版就用 Alembic
- 会话、run、message、trace 分开

### 验证

```bash
alembic upgrade head
pytest tests/unit tests/integration
```

### 完成定义

- 有正式 schema
- CLI/Web 可写同一库

---

## PR4：核心全面异步化 + run 生命周期

### 目标

- 核心执行链改 async
- 落地并发/取消/续跑/重跑语义

### 主要改动目录/文件

- `src/agent/react_engine.py`
- `src/tools/builtin_tools.py`
- `src/tools/tool_registry.py`
- `src/services/run_service.py`

### 关键设计约束

- CLI 用 `asyncio.run(...)`
- 多会话可并发
- 单会话单活跃 run
- cancel 为协作式取消
- rerun 新 run，resume 旧 run

### 验证

```bash
pytest tests/unit/test_react_engine.py
pytest tests/integration/test_run_lifecycle.py
```

### 完成定义

- 异步链路打通
- run 状态机可测

---

## PR5：新 CLI

### 目标

- 子命令式 CLI 落地
- 默认人类可读，支持 `--json`

### 主要改动目录/文件

- `src/cli/commands/run.py`
- `src/cli/commands/conversation.py`
- `src/cli/commands/history.py`
- `main.py`
- `pyproject.toml`

### 关键设计约束

- 包命令为主，脚本兼容
- 默认新会话，可选续接

### 验证

```bash
python -m src.cli.main --help
intelliagent run "测试任务"
intelliagent run "测试任务" --json
```

### 完成定义

- CLI 完全走共享 service
- 不再依赖旧参数风格

---

## PR6：Web 外壳 + HTTP/WS 双轨

### 目标

- Web 服务切到 `src/app.py + src/api/v1/*`
- HTTP 和 WebSocket 共用 service

### 主要改动目录/文件

- `src/app.py`
- `src/api/v1/sessions.py`
- `src/api/v1/runs.py`
- `src/api/v1/ws_runs.py`
- `src/api/deps.py`
- 删除或废弃 `src/web/server.py`

### 关键设计约束

- 默认匿名可用
- 认证代码预留但默认关闭

### 验证

```bash
uvicorn src.app:app --reload
```

手工验证：

- HTTP：建会话 / 建 run / 取消 run
- WebSocket：实时收 event

### 完成定义

- `src/web/server.py` 不再是主入口
- HTTP/WS 不再旁路拼核心

---

## PR7：前端路由壳 + 对话主视图

### 目标

- 前端改为路由壳
- 主视图对话优先，执行痕迹侧展
- 生产由后端托管静态文件

### 主要改动目录/文件

- `frontend/src/App.tsx`
- `frontend/src/routes/*`
- `frontend/src/pages/MainPage.tsx`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/lib/*`
- `scripts/start-web*.sh`

### 关键设计约束

- 匿名模式默认直达主页
- 前端不再把 `logs` 当唯一真相源
- 消息走 message API，痕迹走 trace/WS

### 验证

```bash
cd frontend && npm run build
uvicorn src.app:app
```

手工验证：

- 新建会话
- 运行任务
- cancel / rerun / resume
- 刷新后回放消息与痕迹

### 完成定义

- 前后端契约稳定
- 生产托管闭环完成

---

## 并行关系

- 必须串行：`PR1 → PR2 → PR3 → PR4`
- 可并行：`PR5`（CLI）与 `PR6`（Web API/WS）
- 最后做：`PR7`（前端）

---

## 验收标准

每个切片至少满足：

- 单元测试通过
- 关键集成测试通过
- CLI 冒烟通过
- Web 冒烟通过

建议矩阵：

| 步骤 | 单测 | 集成 | CLI 冒烟 | Web 冒烟 |
|---|---|---|---|---|
| PR1 | 配置加载 | 无 | 入口可导入 | app 可导入 |
| PR2 | runtime/service | 少量 | 兼容入口可走通 | 兼容接口不崩 |
| PR3 | repository/model | migration + SQLite | 可写入会话 | session API 可读写 |
| PR4 | async run/cancel/state | run lifecycle | CLI run/cancel | HTTP + WS 事件 |
| PR5 | CLI commands | CLI + DB | 必做 | 可选 |
| PR6 | API schema/deps | HTTP + WS | 可选 | 必做 |
| PR7 | hooks/adapter | 前后端联调 | 可选 | 必做 |

---

## 不要做的事

1. 不要让 CLI 和 Web 各自 new 一套引擎
2. 不要长期保留 `src/web/server.py` 主路径
3. 不要把 message 和 execution trace 混成一个 `logs` 字段
4. 不要只给 WebSocket 做异步，CLI 留同步旧链
5. 不要让认证变成本地匿名模式的硬依赖
6. 不要跳过 Alembic
7. 不要再做第二套 run 生命周期语义
8. 不要让前端自己维护“权威日志状态”再整包回写数据库
9. 不要继续使用手写 SQLite 初始化替代正式 schema 管理
10. 不要让 `main.py` 同时承担 CLI、Web、核心装配三种职责

# 目录结构说明（统一规划版）

> **文档状态**：规划对齐文档  
> 本文描述的是项目按 `docs/plan.md` 收敛后的**目标目录结构**。  
> 当前仓库仍处于过渡阶段，凡与旧文档中的 `core/`、`src/web/server.py`、`web/frontend/` 等路径冲突之处，统一以 [plan.md](./plan.md) 为准。

---

## 目标结构

```text
intelliagent/
├── src/
│   ├── app.py                    # Web 主入口（FastAPI）
│   ├── cli/                      # 子命令式 CLI
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── commands/
│   ├── config/                   # Pydantic Settings 统一配置
│   ├── runtime/                  # 共享重对象与运行时装配
│   ├── services/                 # 共享执行服务层
│   ├── api/
│   │   └── v1/                   # HTTP / WebSocket API
│   ├── agent/                    # ReAct 核心执行链
│   ├── llm/
│   ├── tools/
│   ├── memory/
│   ├── skills/
│   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   └── session.py
│   └── utils/
├── frontend/                     # 前端项目（路由壳、会话主视图）
├── alembic/                      # 数据库迁移
├── docs/
├── tests/
├── pyproject.toml
└── main.py                       # 兼容入口，不再承担核心装配职责
```

---

## 关键边界

### 1. 入口边界

- **推荐主入口**：包命令 `intelliagent ...`
- **脚本兼容入口**：`main.py`
- **Web 主入口**：`src/app.py`

### 2. 共享核心边界

CLI 与 Web 必须共用：

- `src/runtime/`
- `src/services/`
- `src/agent/`
- `src/tools/`

不得再出现“CLI 一套、Web 一套”的执行链路。

### 3. 数据边界

统一入库，最少包含：

- `users`
- `conversations`
- `runs`
- `messages`
- `execution_traces`（或同等职责表）

消息与执行痕迹必须分离存储。

---

## 明确废弃或降级的旧路径

以下路径若仍出现在旧文档中，仅表示历史阶段实现，不再作为统一规划依据：

- `core/`
- `src/web/server.py`
- `src/web/database.py`
- `web/frontend/`
- `utils/config.py`（最终将降为兼容层或移除）

---

## 相关文档

- [plan.md](./plan.md)：统一实施蓝图
- [PROJECT_DOCUMENTATION.md](./PROJECT_DOCUMENTATION.md)：项目总览
- [QUICK_START.md](./QUICK_START.md)：统一快速入门

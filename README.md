# 🤖 IntelliAgent

> 一个面向代码开发与任务执行的智能代理项目，目标是收敛为 **统一 CLI + Web 双入口、共享核心执行链、统一入库** 的架构。

---

## 当前状态

> **状态说明**：仓库当前仍处于架构收敛阶段。  
> 本 README 描述的是**当前统一方向与推荐理解方式**，不会把尚未完成的规划写成既成事实。  
> 统一实施蓝图请看：[docs/plan.md](docs/plan.md)

这意味着：

- 你在仓库里仍可能看到旧路径、旧脚本和阶段性实现
- 某些旧文档仍记录历史状态，但已补充“历史文档 / 过渡文档 / 规划对齐文档”标记
- 对于架构、目录、入口和数据模型的最终方向，**统一以 `docs/plan.md` 为准**

---

## 项目目标

IntelliAgent 的目标不是单纯的 Web 产品，也不是只做一个 CLI 工具，而是：

- **统一入口，内部共享核心**
- **CLI 与 Web 共用一套执行链路**
- **核心执行链全面异步化**
- **CLI 与 Web 统一入库**
- **默认本地匿名可用，认证作为可选增强**
- **消息与执行痕迹分离存储**

---

## 目标架构

### 1. 入口层

- **CLI**：子命令式接口，包命令为主，脚本兼容
- **Web**：FastAPI + WebSocket，作为另一种入口模式

### 2. 共享核心层

CLI 与 Web 最终应共用：

- `runtime`：共享重对象与运行时装配
- `services`：共享执行服务层
- `agent`：ReAct 执行核心
- `tools`：工具系统
- `llm`：LLM 客户端
- `memory` / `context`：任务级状态对象

### 3. 数据层

统一入库，数据库通过 `DATABASE_URL` 可插拔，默认 SQLite。

核心语义：

- `conversation`：会话上下文
- `run`：一次执行尝试
- `message`：用户可见消息
- `execution trace`：结构化执行痕迹（thought / action / observation / error / complete）

### 4. 运行约束

- 多会话可并发
- 单会话单活跃 run
- `rerun` 新建 run
- `resume` 恢复旧 run
- `cancel` 采用协作式取消

---

## 推荐理解方式

如果你刚进入这个仓库，请按下面顺序理解项目：

1. **先看统一蓝图**：[`docs/plan.md`](docs/plan.md)
2. **再看目标目录**：[`docs/DIRECTORY_STRUCTURE.md`](docs/DIRECTORY_STRUCTURE.md)
3. **再看统一快速入门**：[`docs/QUICK_START.md`](docs/QUICK_START.md)
4. **如果关心 Web**：[`docs/WEB_UI.md`](docs/WEB_UI.md)
5. **如果关心工具系统**：[`docs/TOOLS.md`](docs/TOOLS.md)

---

## 推荐入口（目标形态）

以下是项目收敛后的推荐入口形态：

> PR1 已固定长期入口路径：
>
> - CLI 根入口：`src/cli/main.py`
> - Web 根入口：`src/app.py`
> - 根目录 `main.py` 仅保留兼容转发角色

### CLI

```bash
intelliagent run "你的任务"
```

预期特性：

- 默认创建新会话
- 支持显式续接会话
- 默认输出人类可读内容
- 支持 `--json` 供脚本集成（该能力计划在 PR5 完整落地，当前 PR1 仅固定 CLI 入口骨架）

### Web

```bash
intelliagent web
```

或：

```bash
uvicorn src.app:app
```

预期特性：

- 默认本地匿名可用
- HTTP + WebSocket 双轨执行接口
- 会话为主视图，执行痕迹侧展

> 说明：上面是**目标入口契约**。当前仓库在完全收敛前，仍可能保留兼容性旧入口或阶段性实现。
> 当前阶段建议优先使用 `uvicorn src.app:app` 启动 Web，CLI 则统一走 `src.cli.main` / `intelliagent`。

当前阶段若需显式指定运行时路径，可通过环境变量覆盖：

- `DATABASE_URL`：统一数据库配置字段；**当前 PR1 / 现有数据层仅验证 SQLite 文件 URL**，正式可插拔能力在后续阶段落地
- `WEB_FRONTEND_DIST`：前端构建产物目录
- `WEB_STATIC_DIR`：开发态静态资源目录

---

## 当前仓库里哪些东西不要再当作长期标准

以下内容在仓库中可能仍能看到，但**不再代表统一方向**：

- `core/` 作为核心长期目录
- `src/web/server.py` 作为长期 Web 主入口
- `src/web/database.py` 作为正式数据层实现
- `web/frontend/` 作为长期前端根目录
- `MAX_PDCA_CYCLES`、PDCA 主循环表述
- 把项目默认理解为 Web-only
- 把认证当作本地 Web 启动前置条件

---

## 文档地图

### 核心文档

- [`docs/plan.md`](docs/plan.md)：统一实施蓝图
- [`docs/PROJECT_DOCUMENTATION.md`](docs/PROJECT_DOCUMENTATION.md)：项目总览
- [`docs/DIRECTORY_STRUCTURE.md`](docs/DIRECTORY_STRUCTURE.md)：目标目录结构与边界
- [`docs/QUICK_START.md`](docs/QUICK_START.md)：统一快速入门
- [`docs/VERIFICATION.md`](docs/VERIFICATION.md)：统一验证口径

### Web 相关

- [`docs/WEB_UI.md`](docs/WEB_UI.md)：Web 模式目标形态
- [`docs/QUICK_START_WEB.md`](docs/QUICK_START_WEB.md)：Web 模式快速开始

### 工具系统

- [`docs/TOOLS.md`](docs/TOOLS.md)：工具系统说明
- [`docs/TOOL_INTEGRATION.md`](docs/TOOL_INTEGRATION.md)：MCP 工具集成

### 历史文档

以下文档保留用于回溯历史阶段问题，不作为当前架构依据：

- [`docs/ANALYSIS_SUMMARY.md`](docs/ANALYSIS_SUMMARY.md)
- [`docs/PDCA_OPTIMIZATION_PLAN.md`](docs/PDCA_OPTIMIZATION_PLAN.md)

---

## 路线图概览

统一收敛按以下主线推进：

`PR1 → PR2 → PR3 → PR4 → (PR5 与 PR6 可并行) → PR7`

对应阶段：

1. **统一骨架与配置**
2. **抽共享 runtime/service 层**
3. **数据层 + Alembic 基线**
4. **核心全面异步化 + run 生命周期**
5. **新 CLI**
6. **Web 外壳 + HTTP/WS 双轨**
7. **前端路由壳 + 对话主视图**

详情见 [`docs/plan.md`](docs/plan.md)。

---

## 最小成型标准

第一阶段最小竖切片完成后，应至少满足：

- `intelliagent run "任务"` 可执行
- `uvicorn src.app:app` 可启动
- HTTP 可创建会话与 run
- WebSocket 可实时推送事件
- SQLite 默认可用
- 支持 cancel / rerun / resume

---

## 开发约束

后续开发请遵守这些方向性约束：

1. 不要让 CLI 和 Web 各维护一套执行逻辑
2. 不要把 Web 理解为唯一产品形态
3. 不要让认证成为本地使用前置条件
4. 不要把消息与执行痕迹混存
5. 不要跳过正式 migration 机制
6. 不要继续依赖旧目录和旧入口作为长期标准

---

## 许可证

MIT License

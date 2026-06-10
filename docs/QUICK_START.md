# 快速入门（统一规划版）

> **文档状态**：规划对齐文档  
> 当前仓库仍处于收敛前阶段。本文说明的是**统一方向与推荐用法**，不把尚未落地的规划写成既成事实。  
> 统一实施蓝图见 [plan.md](./plan.md)。

---

## 目标

IntelliAgent 的统一目标是：

- 对外统一入口
- CLI 与 Web 共用一套核心执行链
- 核心执行链全面异步化
- CLI 与 Web 统一入库
- Web 默认本地匿名可用，认证可选增强

---

## 基础准备

### 环境变量

至少需要：

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `DATABASE_URL`（默认规划为 SQLite，可插拔）

后续统一配置将收敛到 Pydantic Settings。

### 安装依赖

```bash
pip install -r requirements.txt
```

> 说明：依赖、配置与启动方式后续会按 `docs/plan.md` 继续收敛。

---

## 目标使用方式

### CLI（规划目标）

```bash
intelliagent run "你的任务"
```

预期行为：

- 默认创建新会话
- 支持显式续接已有会话
- 默认输出人类可读内容
- 支持 `--json` 供脚本消费

### Web（规划目标）

```bash
intelliagent web
```

或：

```bash
uvicorn src.app:app
```

预期行为：

- 默认本地匿名可用
- HTTP + WebSocket 双轨执行接口
- 会话为主视图，执行痕迹侧展

---

## 当前阶段说明

当前仓库中仍可能看到以下旧路径或旧术语：

- `core/`
- `src/web/server.py`
- `web/frontend/`
- `MAX_PDCA_CYCLES`
- PDCA 循环表述

这些内容属于**历史阶段或过渡状态**，不再代表统一规划方向。

---

## 推荐阅读顺序

1. [plan.md](./plan.md)
2. [DIRECTORY_STRUCTURE.md](./DIRECTORY_STRUCTURE.md)
3. [WEB_UI.md](./WEB_UI.md)
4. [TOOLS.md](./TOOLS.md)
5. [TOOL_INTEGRATION.md](./TOOL_INTEGRATION.md)

---

## 统一约束

请按以下原则理解后续文档：

- 不把项目默认理解为 Web-only
- 不允许 CLI 和 Web 各维护一套执行逻辑
- 不把认证当作本地启动前置条件
- 不把消息与执行痕迹混存
- 不把旧入口和旧目录当作未来推荐实现

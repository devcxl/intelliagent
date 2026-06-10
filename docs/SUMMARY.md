# 统一收敛摘要

> **文档状态**：规划对齐摘要  
> 本文替代旧的“Web UI 优化总结”作为统一架构摘要。  
> 详细实施步骤见 [plan.md](./plan.md)。

---

## 目标方向

IntelliAgent 将收敛为：

- 统一入口
- CLI 与 Web 共享核心
- 核心执行链异步化
- 统一入库
- 默认本地匿名可用
- 认证可选增强

---

## 结构变化

从旧的阶段性实现收敛到以下方向：

- `main.py`：兼容入口，不再承担核心装配
- `src/app.py`：Web 主入口
- `src/api/v1/*`：HTTP / WebSocket API
- `src/runtime/*`、`src/services/*`：共享执行边界
- `frontend/`：前端项目根目录
- `alembic/`：正式 schema 演进

---

## 数据与运行模型

- 会话与执行分离：`conversation` / `run`
- 消息与执行痕迹分离：`message` / `execution trace`
- 多会话可并发，单会话单活跃 run
- 重跑新 run，续跑旧 run
- 取消采用协作式取消

---

## 文档使用方式

优先阅读：

1. [plan.md](./plan.md)
2. [DIRECTORY_STRUCTURE.md](./DIRECTORY_STRUCTURE.md)
3. [QUICK_START.md](./QUICK_START.md)
4. [WEB_UI.md](./WEB_UI.md)
5. [VERIFICATION.md](./VERIFICATION.md)

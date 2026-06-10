# IntelliAgent 项目文档

> **文档状态**：总览文档  
> 本文提供项目概览与文档导航。统一规划与实施顺序以 [plan.md](./plan.md) 为准。

---

## 1. 项目概述

IntelliAgent 是一个面向代码开发与任务执行的智能代理项目，目标是收敛为：

- 统一入口
- CLI 与 Web 共享核心执行链
- ReAct 异步执行模型
- 统一入库与可审计运行记录

---

## 2. 目标架构

核心组成：

- **CLI 入口**：子命令式接口，包命令为主，脚本兼容
- **Web 入口**：`src/app.py + src/api/v1/*`
- **共享运行时**：`src/runtime/*`
- **共享服务层**：`src/services/*`
- **执行核心**：`src/agent/react_engine.py`
- **工具系统**：`src/tools/*`
- **数据层**：`src/db/*` + Alembic

---

## 3. 关键运行原则

- Web 不是唯一入口模式
- 认证默认关闭，本地匿名模式可直接使用
- 消息与执行痕迹分离存储
- 多会话可并发，单会话单活跃 run

---

## 4. 推荐阅读

- [plan.md](./plan.md)
- [DIRECTORY_STRUCTURE.md](./DIRECTORY_STRUCTURE.md)
- [QUICK_START.md](./QUICK_START.md)
- [WEB_UI.md](./WEB_UI.md)
- [TOOLS.md](./TOOLS.md)
- [TOOL_INTEGRATION.md](./TOOL_INTEGRATION.md)

---

## 5. 历史文档

以下文档保留用于回溯历史问题与旧方案，不作为当前统一规划依据：

- [ANALYSIS_SUMMARY.md](./ANALYSIS_SUMMARY.md)
- [PDCA_OPTIMIZATION_PLAN.md](./PDCA_OPTIMIZATION_PLAN.md)

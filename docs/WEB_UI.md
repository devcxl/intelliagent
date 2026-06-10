# Web UI 说明（统一规划版）

> **文档状态**：规划对齐文档  
> 本文描述的是 Web 模式的**目标形态**。  
> 旧的 `src/web/server.py`、`web/frontend/`、单纯日志主视图等内容不再作为统一方向依据，统一以 [plan.md](./plan.md) 为准。

---

## Web 模式定位

Web 不是项目的唯一形态，而是与 CLI 并列的一种入口模式。

统一目标：

- 与 CLI 共用一套核心执行链
- 默认本地匿名可用
- 认证能力预留，但默认关闭
- 会话主视图优先，执行痕迹可追踪

---

## 目标架构

### 后端

- `src/app.py`：FastAPI 主入口
- `src/api/v1/*`：HTTP / WebSocket API
- `src/services/*`：共享运行服务
- `src/runtime/*`：共享重对象装配

### 前端

- `frontend/`：前端项目根目录
- 路由壳结构
- 匿名模式默认直达主页面

---

## 目标交互模型

### 主视图

- 左侧：会话列表
- 中间：对话主视图
- 侧展/抽屉：执行痕迹（thought / action / observation / error / complete）

### 执行接口

- HTTP：创建会话、创建 run、查询状态、取消、重跑、续跑
- WebSocket：实时推送执行事件

### 数据语义

- `conversation` 承载会话上下文
- `run` 承载一次执行尝试
- `message` 承载用户可见消息
- `execution trace` 承载结构化执行痕迹

---

## 目标运行方式

### 本地开发

规划目标：

```bash
uvicorn src.app:app --reload
```

前端开发模式将继续保留独立构建与热更新能力，但统一路径以 `frontend/` 为准，而不是旧的 `web/frontend/`。

### 生产部署

规划目标：

- 后端托管构建后的前端静态资源
- API 与静态托管共用统一应用入口

---

## 非目标

以下不再视为统一规划目标：

- 把 Web 视为项目唯一入口
- 继续以 `src/web/server.py` 作为长期主入口
- 把执行日志当作唯一主视图
- 默认强制登录后才能使用本地 Web

# Web 模式快速开始（统一规划版）

> **文档状态**：规划对齐文档  
> 本文描述的是 Web 模式的推荐启动方式与目标行为。  
> 旧的 `python web/server.py`、`web/frontend/` 等路径属于历史阶段实现，不再作为统一方向推荐。

---

## 目标启动方式

### 方式一：统一 CLI 入口

```bash
intelliagent web
```

### 方式二：直接启动应用

```bash
uvicorn src.app:app
```

---

## 目标访问效果

访问后应满足：

- 默认本地匿名可用
- 可创建会话
- 可发起任务执行
- 可通过 WebSocket 看到实时事件流
- 支持 cancel / rerun / resume

---

## 当前阶段说明

在统一规划完全落地前，仓库中可能仍保留旧脚本、旧路径和旧启动方式。它们可以作为过渡参考，但不再是统一文档推荐路径。

统一规范以以下文档为准：

- [plan.md](./plan.md)
- [WEB_UI.md](./WEB_UI.md)
- [VERIFICATION.md](./VERIFICATION.md)

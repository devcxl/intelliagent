# 统一规划验证说明

> **文档状态**：规划对齐文档  
> 本文给出的是统一收敛后的**目标验证口径**，不是对当前仓库状态的通过声明。  
> 详细阶段划分见 [plan.md](./plan.md)。

---

## 验证原则

- 不把未执行的命令写成“已通过”
- 每个切片至少覆盖：单测、集成、CLI 冒烟、Web 冒烟
- CLI 与 Web 的验证都必须经过共享执行链

---

## 分层验证矩阵

| 层级 | 目标 | 最低验证 |
|---|---|---|
| 配置层 | 统一 Settings 可加载 | 配置导入、关键环境变量解析 |
| 核心执行层 | 异步 ReAct 链路可运行 | `react_engine` 单测 + 运行生命周期集成测试 |
| 数据层 | 统一入库与 migration 正常 | `alembic upgrade head` + repository 集成测试 |
| CLI 层 | 子命令通过共享 service 执行 | `run` / `conversation` 冒烟 |
| API 层 | HTTP + WebSocket 双轨正确 | run 创建、取消、事件流测试 |
| 前端层 | 会话主视图与痕迹侧展可用 | 手工冒烟 + 前后端联调 |

---

## 目标验证命令

### 单元测试

```bash
pytest tests/unit
```

### 集成测试

```bash
pytest tests/integration
```

### 数据迁移

```bash
alembic upgrade head
```

### Web 启动验证（目标路径）

```bash
uvicorn src.app:app
```

### CLI 验证（目标路径）

```bash
intelliagent run "测试任务"
intelliagent run "测试任务" --json
```

---

## 注意

以下旧验证口径不再作为统一标准：

- 仅验证 `src/web/server.py`
- 仅验证旧脚本可启动
- 仅验证前端静态资源存在
- 把单次手工验证写成长期架构结论

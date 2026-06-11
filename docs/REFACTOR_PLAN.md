# IntelliAgent 架构重构方案

> 2026-06-11 | 分支：loop

---

## 一、目标

消除分层违规，清理死代码，统一数据访问，明确模块职责。不改变功能行为，仅调整模块归属和依赖方向。

---

## 二、当前 vs 目标分层

```
当前（混乱）                          目标（清晰）

main.py (兼容入口)                    main.py (兼容入口)
src/cli/main.py (CLI)                src/cli/main.py (CLI)
src/web/server.py (Web + 旧端点)      src/web/server.py (纯 Web 入口)
src/web/database.py (数据访问!)       src/web/static/ (静态文件)
src/api/v1/ (新路由)                 src/api/v1/ (API 路由)
src/services/ (业务)                 src/services/ (业务编排)
src/runtime/ (工厂 + 单例)           src/runtime/ (运行时工厂)
src/agent/ (引擎 + 死代码)           src/agent/ (ReAct 引擎)
src/llm/ (LLM 客户端)               src/llm/ (LLM 客户端)
src/tools/ (工具)                    src/tools/ (工具)
src/memory/ (记忆)                   src/memory/ (记忆)
src/skills/ (死代码)                 [删除]
src/db/ (ORM + Repository)          src/db/ (ORM + Repository)
src/config/ (Settings)              src/config/ (Settings)
utils/config.py (兼容层)             [删除，合并到 src/config/]
```

---

## 三、分阶段执行

### 阶段 1：清理死代码（低风险，纯删除）

| 操作 | 文件 | 说明 |
|------|------|------|
| 删除 | `src/agent/executor.py` | PDCA 遗留，未被任何模块引用 |
| 删除 | `src/skills/skill.py` | 旧 CodeSkill 系统 A |
| 删除 | `src/skills/skill_manager.py` | 旧 SkillManager |
| 删除 | `src/skills/skill_system.py` | 新 Skill 系统 B |
| 删除 | `src/skills/skill_loader.py` | SkillLoader |
| 删除 | `src/skills/skill_integration.py` | SkillIntegration |
| 删除 | `src/skills/__init__.py` | 空文件 |
| 删除 | `tests/unit/test_skill.py.disabled` | 已禁用测试 |
| 删除 | `tests/unit/test_skill_new.py` | 依赖不存在的 Skill 数据 |
| 删除 | `tests/unit/test_pdca_integration.py.disabled` | 已禁用测试 |

**验证**：`git grep "from src.skills"` 和 `git grep "from src.agent.executor"` 无结果。

### 阶段 2：消除分层违规（中风险，调整依赖）

#### 2.1 将 `DatabaseManager` 从 `src/web/` 迁移到 `src/db/`

```
src/web/database.py → src/db/manager.py
```

`DatabaseManager` 本质是数据访问层，不应放在 web 层。迁移后：
- `SessionService` 不再依赖 `src.web/`，违规消除
- `src/web/server.py` 和 `src/cli/main.py` 从 `src/db.manager` 导入

#### 2.2 `SessionService` 直接依赖 Repository

当前 `SessionService` 是 `DatabaseManager` 的透传封装。改为直接依赖 `ConversationRepository`：

```python
# 之前
class SessionService:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

# 之后
class SessionService:
    def __init__(self, conversation_repo: ConversationRepository):
        self.conversation_repo = conversation_repo
```

`DatabaseManager` 保留作为过渡兼容层，标记 `@deprecated`，后续阶段移除。

#### 2.3 删除 `utils/config.py`

`utils/config.py` 只是 `src/config/settings.py` 的兼容层。全局替换所有 `from utils.config import X` 为 `from src.config import get_settings` + `settings.X`。

**影响范围**：
- `src/agent/react_engine.py`
- `src/llm/llm_client.py`
- `src/tools/tool_registry.py`
- `src/memory/memory.py`
- `src/web/server.py`
- `src/web/database.py`（迁移后为 `src/db/manager.py`）

### 阶段 3：精简 `src/web/server.py`（中风险，拆分职责）

当前 `server.py` 约 470 行，职责混杂。拆分为：

```
src/web/
  server.py       -- FastAPI 应用工厂 + 生命周期（~150 行）
  routes.py       -- 旧 API 端点（/api/run, /api/sessions, /ws/run）（~150 行）
  static.py       -- 静态文件配置（~80 行）
  database.py     -- [阶段 2 迁移后删除]
```

`routes.py` 中的旧端点标记 `@deprecated`，引导调用方迁移到 `src/api/v1/`。

### 阶段 4：统一 API 路由（中风险，消除重复）

当前两套路由并存：
- `src/web/server.py` 直接定义 `/api/sessions`, `/api/runs/cancel`
- `src/api/v1/` 定义 `/api/v1/conversations`, `/api/v1/runs`

**方案**：
1. 确认前端是否已迁移到 v1 路由
2. 如已迁移，删除 `server.py` 中的旧端点
3. 如未迁移，先更新前端，再删除旧端点

### 阶段 5：合并 Memory 和 Context（低风险，消除重叠）

`ContextManager` 仅保留 10 条字符串，功能与 `Memory` 重叠。合并方案：

```python
class Memory:
    # 已有：观察记录 + 经验持久化
    # 新增：上下文历史（替代 ContextManager）
    
    def add_context(self, text: str) -> None: ...
    def get_context(self) -> str: ...
```

删除 `src/memory/context.py`，`ReactEngine` 和 `AgentRuntime` 中移除 `ContextManager` 引用。

### 阶段 6：重命名 PDCA 残留

| 位置 | 当前名称 | 改为 |
|------|---------|------|
| `src/config/settings.py` | `MAX_PDCA_CYCLES` | `MAX_REACT_ITERATIONS` |
| `src/config/settings.py` | `MAX_RETRY_PER_STEP` | 评估是否仍在使用 |
| `src/llm/llm_client.py` | 注释中的 "PDCA 循环" | "ReAct 循环" |

---

## 四、执行顺序

```
阶段 1（清理死代码）
  └── 验证：无引用残留
        │
阶段 2（消除分层违规）
  ├── 2.1 迁移 DatabaseManager
  ├── 2.2 重构 SessionService
  └── 2.3 删除 utils/config.py
        │
阶段 3（拆分 server.py）
        │
阶段 4（统一 API 路由）
        │
阶段 5（合并 Memory/Context）
        │
阶段 6（重命名 PDCA 残留）
```

每个阶段独立提交，可单独回滚。

---

## 五、最终分层

```
main.py                    # 兼容入口
src/cli/main.py            # CLI 入口
src/web/server.py          # FastAPI 应用工厂
src/web/routes.py          # 旧端点（deprecated）
src/web/static.py          # 静态文件配置
src/api/v1/                # API 路由
src/services/              # 业务编排
src/runtime/               # 运行时工厂
src/agent/react_engine.py  # ReAct 引擎
src/llm/llm_client.py      # LLM 客户端
src/tools/                 # 工具系统
src/memory/memory.py       # 记忆管理（合并 Context）
src/db/                    # 数据访问层
src/db/manager.py          # DatabaseManager（deprecated）
src/config/settings.py     # 统一配置
alembic/                   # 数据库迁移
```

**依赖方向**：入口 -> API -> 服务 -> 领域 -> 基础设施。无循环，无向上依赖。

---

## 六、风险与验证

| 阶段 | 风险 | 验证方式 |
|------|------|---------|
| 1 | 误删被间接引用的代码 | `git grep` 全量搜索 + `pytest` |
| 2 | 导入路径变更导致运行时错误 | `python -c "from src.db.manager import DatabaseManager"` |
| 3 | 路由注册遗漏 | `curl localhost:8000/api/sessions` |
| 4 | 前端依赖旧端点 | 检查前端 `session-api.ts` 调用的端点 |
| 5 | ReactEngine 依赖 ContextManager | 搜索 `context` 引用 |
| 6 | 配置项名称变更影响下游 | 搜索 `MAX_PDCA_CYCLES` 引用 |

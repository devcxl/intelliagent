## Agent Brief

**类别：** enhancement
**摘要：** 按 SOLID 原则重构 5 个模块：PermissionEngine 策略化（OCP）、ToolRegistry 装饰器注册（OCP）、DatabaseManager 仓储拆分（ISP/SRP）、AgentRuntime 依赖注入（DIP）、main.py 关注点分离（SRP）。

**关联 Issue：** [#4](https://github.com/devcxl/intelliagent/issues/4)

---

## 当前行为

### Step A — PermissionEngine 条件判断硬编码（OCP 违反）

`PermissionEngine._evaluate_condition()` 通过 `if key == "dangerous": ... elif key == "path_in_workspace": ... elif key == "path_sensitive": ...` 硬编码 3 种条件判断。添加新条件类型（如 `network_access`、`file_size_limit`）必须修改 `_evaluate_condition` 方法本身。

相关条件函数已作为模块级函数存在：
- `_is_dangerous_cmd(cmd_str: str) -> bool`
- `_is_path_sensitive(cmd_str: str) -> bool`
- `_is_path_in_workspace(path: str, workspace: Path) -> bool`

`PermissionEngineProtocol` 已在 `src/types/permission.py` 中定义，`check()` 签名不变。

### Step B — ToolRegistry 静态字典注册（OCP 违反）

`src/tools/registry.py` 中 `BUILTIN_TOOLS` 是一个模块级静态字典，所有工具函数和参数 schema 硬编码其中。添加新工具必须修改该字典。`get_openai_tools()`、`get_tool_fn()`、`list_tool_names()`、`call_tool()` 全部直接引用 `BUILTIN_TOOLS`。

`ReactEngine.__init__()` 已接受 `tools_registry` 参数（默认 `_default_registry`），但 `_default_registry` 实际是模块级函数而非类实例。

### Step C — DatabaseManager 胖类（ISP/SRP 违反）

`DatabaseManager`（419 行）一个类同时管理 5 张表（users、conversations、messages、runs、execution_traces）的 CRUD。调用方（`main.py`、`run_service.py`）依赖了整个 `DatabaseManager`，但实际只需要其中 2-3 张表的方法。

当前方法列表：
- Conversation: `create_conversation`, `get_conversation`, `update_conversation`, `delete_conversation`, `list_conversations`, `get_latest_conversation`
- Message: `save_message`, `get_messages`
- Run: `create_run`, `get_run`, `update_run`, `list_runs_by_conversation`
- Trace: `save_trace`, `list_traces_by_run`
- 初始化: `initialize`

### Step D — AgentRuntime 直接依赖具体类（DIP 违反）

`AgentRuntime.get_llm_client()` 直接 `LLMClient(...)` 实例化，而非依赖 `LLMClientProtocol`。

`AgentRuntime.create_engine()` 内部直接 `load_permission_engine(...)` + `CliCallback(...)`，硬编码具体实现。

已有 Protocol 定义（`src/types/permission.py`）：
- `LLMClientProtocol` — `chat_async()` 签名
- `PermissionEngineProtocol` — `check()` 签名
- `PermissionCallbackProtocol` — `on_prompt()` 签名

### Step E — main.py 单一函数混合关注点（SRP 违反）

`main()` 函数（约 170 行）混合了：
1. CLI 参数解析（argparse）
2. 数据库初始化与 Conversation 生命周期管理
3. 引擎创建与执行
4. 事件循环中的输出格式化（print + trace 保存）
5. 收尾的状态更新

`_show_history()` 是独立的展示函数，但也在同一文件中。

---

## 期望行为

### Step A — PermissionEngine 策略模式

- `_evaluate_condition` 不再包含 `if-elif` 分支
- 定义 `ConditionStrategy` 协议/接口：`evaluate(args: dict, workspace: Path) -> bool`
- 每种条件类型实现为一个独立策略类（`DangerousCondition`、`PathSensitiveCondition`、`PathInWorkspaceCondition`）
- `PermissionEngine` 通过字典 `{condition_name: ConditionStrategy}` 注册策略
- 添加新条件类型只需：实现 `ConditionStrategy` + 注册到字典，不修改 `_evaluate_condition`
- `PermissionEngine.check()` 对外行为完全不变
- `load_permission_engine()` 工厂函数行为不变

### Step B — ToolRegistry 装饰器注册

- 提供 `@tool(name, description, parameters)` 装饰器，将函数注册到 `ToolRegistry` 实例
- `ToolRegistry` 变为类（而非模块级函数），实例方法：`register(fn, name, description, parameters)`、`get_openai_tools()`、`get_tool_fn(name)`、`list_tool_names()`
- 现有 5 个内置工具（`run_shell`、`read_file`、`write_file`、`edit_file`、`todo_write`）通过装饰器注册
- 添加新工具只需：写函数 + `@tool(...)` 装饰，不修改 registry 内部数据结构
- `ReactEngine` 通过构造函数接收 `ToolRegistry` 实例（已有 `tools_registry` 参数）
- `get_openai_tools()` 和 `get_tool_fn()` 对外行为不变

### Step C — DatabaseManager 仓储拆分

- 按表拆分为 4 个独立仓储类：
  - `ConversationRepository` — conversations 表 CRUD + `get_latest_conversation()`
  - `MessageRepository` — messages 表 CRUD
  - `RunRepository` — runs 表 CRUD + `list_runs_by_conversation()`
  - `TraceRepository` — execution_traces 表 CRUD + `list_traces_by_run()`
- 每个仓储构造函数接收 `db_path: str`（SQLite 文件路径）
- 每个仓储仅暴露自己表的操作方法，不包含其他表的方法
- `initialize()` 建表逻辑提取为独立函数或保留在 `DatabaseManager` 中（向后兼容）
- 原 `DatabaseManager` 保留为 Facade，内部委托给各仓储（可选，如调用方过多）
- 所有 CRUD 方法签名和返回值格式不变
- `delete_conversation` 的级联删除逻辑保留在 `ConversationRepository` 中

### Step D — AgentRuntime 依赖注入

- `AgentRuntime.__init__()` 接受可选的工厂参数：
  - `llm_client_factory: Callable[[], LLMClientProtocol] | None`
  - `permission_engine_factory: Callable[[], PermissionEngineProtocol] | None`
  - `permission_callback_factory: Callable[[], PermissionCallbackProtocol] | None`
- 默认工厂保持当前行为（创建 `LLMClient`、`load_permission_engine`、`CliCallback`）
- `get_llm_client()` 返回类型标注为 `LLMClientProtocol`
- `create_engine()` 通过工厂创建依赖，而非直接实例化具体类
- 测试可通过注入 mock 工厂替换所有依赖
- 对外 API（`create_engine()` 返回值、`get_llm_client()` 返回值）行为不变

### Step E — main.py 关注点分离

- 拆分为 3 个模块：
  - `src/cli/parser.py` — argparse 定义与参数解析（纯函数，无副作用）
  - `src/cli/orchestrator.py` — Conversation 生命周期管理（创建/恢复/执行/状态更新），依赖仓储接口
  - `src/cli/presenter.py` — 输出格式化（事件打印、历史列表展示）
- `main()` 函数精简为组合调用：解析参数 → 编排执行 → 展示结果
- `_show_history()` 迁移到 presenter 模块
- 事件循环中的 print + trace 保存逻辑分离：presenter 负责 print，orchestrator 负责 trace 保存
- CLI 参数（`--resume`、`--session`、`--history`）行为完全不变

---

## 关键接口

### Step A — ConditionStrategy

```python
# src/core/permission_engine.py（新增）

from typing import Protocol

class ConditionStrategy(Protocol):
    """条件评估策略接口 — 每种条件类型实现此协议。"""
    def evaluate(self, args: dict[str, Any], workspace: Path) -> bool: ...

# 内置策略注册表
CONDITION_STRATEGIES: dict[str, ConditionStrategy] = {
    "dangerous": DangerousCondition(),
    "path_in_workspace": PathInWorkspaceCondition(),
    "path_sensitive": PathSensitiveCondition(),
}
```

`PermissionEngine._evaluate_condition()` 改为：
```python
def _evaluate_condition(self, conditions, args):
    if not conditions:
        return True
    for key, expected in conditions.items():
        strategy = CONDITION_STRATEGIES.get(key)
        if strategy is None:
            return False  # 未知条件类型
        actual = strategy.evaluate(args, self._workspace)
        if actual != expected:
            return False
    return True
```

### Step B — ToolRegistry 类 + @tool 装饰器

```python
# src/tools/registry.py（重构后）

class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDef] = {}

    def register(self, fn: ToolFn, name: str, description: str,
                 parameters: dict[str, dict[str, Any]]) -> None:
        self._tools[name] = ToolDef(name=name, description=description,
                                     function=fn, parameters=parameters)

    def tool(self, name: str, description: str,
             parameters: dict[str, dict[str, Any]]) -> Callable:
        """装饰器：@registry.tool(name='...', description='...', parameters={...})"""
        def decorator(fn: ToolFn) -> ToolFn:
            self.register(fn, name, description, parameters)
            return fn
        return decorator

    def get_openai_tools(self) -> list[dict[str, Any]]: ...
    def get_tool_fn(self, name: str) -> ToolFn | None: ...
    def list_tool_names(self) -> list[str]: ...
```

### Step C — 仓储接口

```python
# src/db/repositories.py（新增）

class ConversationRepository:
    def __init__(self, db_path: str) -> None: ...
    async def create(conversation_id, title, task, status) -> dict: ...
    async def get(conversation_id) -> dict | None: ...
    async def update(conversation_id, title, status) -> bool: ...
    async def delete(conversation_id) -> bool: ...
    async def list_all() -> list[dict]: ...
    async def get_latest() -> dict | None: ...

class MessageRepository:
    def __init__(self, db_path: str) -> None: ...
    async def save(conversation_id, role, content) -> str: ...
    async def list_by_conversation(conversation_id) -> list[dict]: ...

class RunRepository:
    def __init__(self, db_path: str) -> None: ...
    async def create(run_id, conversation_id, task_snapshot, ...) -> dict: ...
    async def get(run_id) -> dict | None: ...
    async def update(run_id, status, current_iteration, cancel_requested) -> bool: ...
    async def list_by_conversation(conversation_id) -> list[dict]: ...

class TraceRepository:
    def __init__(self, db_path: str) -> None: ...
    async def save(trace_id, run_id, iteration, trace_type, data) -> str: ...
    async def list_by_run(run_id) -> list[dict]: ...
```

### Step D — AgentRuntime 构造函数变更

```python
# src/runtime/agent_runtime.py（重构后）

class AgentRuntime:
    def __init__(
        self,
        settings: Any,
        llm_client_factory: Callable[[], LLMClientProtocol] | None = None,
        permission_engine_factory: Callable[[], PermissionEngineProtocol] | None = None,
        permission_callback_factory: Callable[[], PermissionCallbackProtocol] | None = None,
    ) -> None: ...

    def get_llm_client(self) -> LLMClientProtocol: ...
    def create_engine(self, ...) -> ReactEngine: ...
```

### Step E — CLI 模块拆分

```
src/cli/
    __init__.py
    parser.py        # build_parser() -> ArgumentParser
    orchestrator.py  # ConversationOrchestrator 类
    presenter.py     # format_event(), show_history()
```

`main()` 简化为：
```python
async def main(task, session_id, resume, list_history):
    settings = get_settings()
    orchestrator = ConversationOrchestrator(settings)
    if list_history:
        presenter.show_history(await orchestrator.list_conversations())
        return
    async for event in orchestrator.execute(task, session_id, resume):
        presenter.format_event(event)
    presenter.show_summary(orchestrator.result)
```

---

## 验收标准

### Step A — PermissionEngine 策略模式
- [ ] `_evaluate_condition` 方法不包含 `if key == "dangerous"` 等硬编码分支
- [ ] `ConditionStrategy` 协议定义清晰，3 个内置策略类独立可测试
- [ ] 添加新条件类型只需新增策略类 + 注册到 `CONDITION_STRATEGIES`，不修改 `_evaluate_condition`
- [ ] `PermissionEngine.check()` 对相同输入返回相同 `Decision`
- [ ] 现有 `test_permission_engine.py` 和 `test_permission_integration.py` 全部通过

### Step B — ToolRegistry 装饰器注册
- [ ] `ToolRegistry` 是类而非模块级函数集合
- [ ] `@registry.tool(name=..., description=..., parameters={...})` 装饰器可用
- [ ] 5 个内置工具通过装饰器注册
- [ ] `get_openai_tools()` 和 `get_tool_fn()` 返回结果与重构前一致
- [ ] `ReactEngine` 通过构造函数接收 `ToolRegistry` 实例
- [ ] 现有 `test_builtin_tools.py` 全部通过

### Step C — DatabaseManager 仓储拆分
- [ ] 4 个独立仓储类（Conversation/Message/Run/Trace），每个仅包含自己表的方法
- [ ] 所有 CRUD 方法签名和返回值格式不变
- [ ] `delete_conversation` 级联删除逻辑正确
- [ ] `main.py` 和 `run_service.py` 通过仓储接口访问数据库
- [ ] 现有 `test_database_manager.py` 全部通过（或等价覆盖）

### Step D — AgentRuntime 依赖注入
- [ ] `AgentRuntime.__init__()` 接受 3 个可选工厂参数
- [ ] 默认工厂行为与重构前一致
- [ ] `get_llm_client()` 返回类型标注为 `LLMClientProtocol`
- [ ] `create_engine()` 不直接 `LLMClient(...)`、不直接 `load_permission_engine(...)`、不直接 `CliCallback(...)`
- [ ] 测试可通过注入 mock 工厂替换所有依赖
- [ ] 现有 `test_runtime_services.py` 全部通过

### Step E — main.py 关注点分离
- [ ] `src/cli/` 目录包含 `parser.py`、`orchestrator.py`、`presenter.py`
- [ ] `main()` 函数不超过 30 行
- [ ] CLI 参数解析逻辑在 `parser.py` 中，无副作用
- [ ] Conversation 生命周期管理在 `orchestrator.py` 中
- [ ] 输出格式化在 `presenter.py` 中
- [ ] `--resume`、`--session`、`--history` 行为与重构前一致
- [ ] 现有 `test_main.py` 全部通过（或等价覆盖）

### 全局验收
- [ ] 5 个步骤按 A→B→C→D→E 顺序执行，每步完成后独立可验证
- [ ] 所有现有测试（`tests/` 下全部）通过
- [ ] 不引入新的第三方依赖
- [ ] 不改变对外 API（CLI 命令、`ReactEngine.run()`、`ReactEngine.iter_steps()`）

---

## 不在范围内

- 不修改 `ReactEngine._loop()` 核心循环逻辑
- 不修改 `ContextManager` 的任何行为
- 不修改 `LLMClient` 的实现
- 不修改 `PermissionCallback`（`CliCallback`）的实现
- 不修改数据库 schema（`_SCHEMA_SQL`）
- 不修改 `src/config/settings.py` 配置定义
- 不修改 `src/types/permission.py` 中已有的 Protocol 定义（仅新增 `ConditionStrategy`）
- 不引入 ORM 框架（如 SQLAlchemy）
- 不引入依赖注入容器框架
- 不修改 `src/utils/logger.py`
- 不新增功能特性，仅重构现有代码结构
- 不修改 `run_service.py` 的对外接口（内部调用方式可随 Step C/D 调整）

---

## 风险点及对策

| 风险 | 影响 | 对策 |
|------|------|------|
| 仓储拆分后 `delete_conversation` 级联删除跨多个仓储 | 数据不一致 | `ConversationRepository` 构造函数接收其他仓储引用，或保留在 Facade 层 |
| `@tool()` 装饰器改变工具注册时机 | 循环导入 | 装饰器在模块加载时执行，保持与 `BUILTIN_TOOLS` 相同的导入顺序 |
| `AgentRuntime` 工厂参数过多 | 调用方负担 | 默认参数保持向后兼容，仅测试需要显式注入 |
| `main.py` 拆分后事件循环中的 trace 保存与 print 耦合 | 逻辑分散 | orchestrator 负责 trace 保存，presenter 负责 print，通过事件流解耦 |
| 重构导致现有测试大量失败 | 阻塞交付 | 每步完成后立即运行测试，小步提交 |

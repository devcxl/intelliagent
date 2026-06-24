# ADR 0006: SOLID 重构 — 模块边界清理

## 状态

已实施

## 背景

随着项目发展，部分模块出现了职责边界模糊、依赖混乱的问题。主要痛点：

- `PermissionEngine` 与 `ToolRegistry` 紧耦合
- `DB` 层所有逻辑堆在 `Repository` 类中
- `AgentRuntime` 既是工厂又是服务
- `main.py` 中混杂 CLI 解析、对话循环和引擎创建
- 部分模块缺乏依赖注入，难以替换和测试

## 决策

对 5 个模块进行 SOLID 重构，核心原则：**每个模块只做一件事，依赖通过构造函数注入**。

## 详细设计

### 1. PermissionEngine — 策略化（OCP/DIP）

- 引入 `ConditionStrategy` 策略接口，每种条件（`path_in_workspace`、`dangerous` 等）一个策略类
- `PermissionEngine` 从 `StrategyRegistry` 获取策略，不再直接实现检查逻辑
- 后续重构（ADR 0003）进一步简化，用 fnmatch + last-match-wins 替代策略类体系

### 2. ToolRegistry — 装饰器模式（OCP）

- 新增 `@registry.tool()` 装饰器，简化工具注册
- 支持装饰器和手动注册两种方式
- 工具定义使用 `ToolDef` 数据类

### 3. DB 仓储拆分（SRP）

- `MessageRepository`、`ConversationRepository`、`TaskRepository` 各司其职
- 每个 Repository 只操作一个表
- 通过 session factory 注入依赖

### 4. AgentRuntime — DI（DIP）

- 接受 `llm_client_factory`、`permission_engine_factory`、`permission_callback_factory` 三个工厂函数
- 每个工厂有默认实现（`_default_*_factory`）
- 未传入时自动从 `UnifiedConfig` 加载

### 5. main.py 拆分（SRP）

- CLI 解析 → `src/cli/parser.py`
- 输出格式化 → `src/cli/presenter.py`
- 对话编排 → `src/runtime/conversation_orchestrator.py`
- `main.py` 仅保留入口逻辑

## 理由

- **SRP**：每个类职责单一，便于理解和测试
- **DIP**：高层模块不依赖低层实现，通过工厂/抽象解耦
- **OCP**：新增工具只需注册，新增条件只需实现策略接口
- **测试性**：依赖注入使得 mock 替换更容易

## 后果

- `AgentRuntime` 的构造参数增加，但默认值保证了向后兼容
- 工具注册方式更灵活，但需注意装饰器执行顺序
- `main.py` 行数减少约 60%，`src/cli/` 和 `src/runtime/` 包新增

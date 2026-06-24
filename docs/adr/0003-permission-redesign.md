# ADR 0003: 权限引擎重构

## 状态

已实施

## 背景

原有的 PermissionEngine 基于 ConditionStrategy 策略类体系，每个条件类型（`path_in_workspace`、`dangerous` 等）有一个独立策略类，使用 first-match-wins 匹配规则。问题：

- 策略类过多导致代码膨胀，难以理解和扩展
- first-match-wins 语义不直观，用户无法覆盖前面的默认规则
- 条件系统与 opencode 等主流 Agent 框架的模式不兼容
- 动作级别使用 `prompt` 而非更直观的 `ask`

## 决策

采用 opencode 风格的 fnmatch 模式匹配 + last-match-wins 权限机制，彻底替换 ConditionStrategy 策略类体系。

## 详细设计

### 模块结构

```
src/permission/
├── __init__.py    统一公共 API 导出
├── types.py       类型定义（PermissionAction, Decision, Protocols）
├── engine.py      权限引擎（规则匹配 + 安全检查）
└── callback.py    CLI 交互确认（CliCallback）
```

### 规则匹配

```python
_match_rule(pattern, tool_name, args):
    1. 工具名匹配：pattern 去空格后 fnmatch 匹配工具名
    2. 参数值匹配：原始 pattern fnmatch 匹配每个字符串参数
```

### 检查优先级

1. 用户规则（last-match-wins）
2. 安全检查（路径越界 + 不在外部白名单 → deny）
3. 默认规则（last-match-wins）
4. 绝对兜底（无匹配 → ask）

### 默认规则

| Pattern | Action |
|---------|--------|
| `*` | ask |
| `read *` | allow |
| `.env*` | deny |
| `skill *` | allow |
| `edit *` | ask |
| `bash *` | ask |
| `write *` | ask |

### 配置模型

配置模型 `PermissionRule` / `PermissionsConfig` 定义在 `src/config/unified_config.py`，权限模块通过 `TYPE_CHECKING` 导入（运行时无循环依赖）。

## 理由

- **与主流对齐**：opencode 等成熟框架已验证该模式的有效性
- **更少的代码**：删除 ~120 行（策略类体系），逻辑更直观
- **用户可控**：last-match-wins 允许用户覆盖任意默认行为
- **配置即策略**：用户只需写 pattern + action，无需理解策略类

## 后果

- 旧 `permissions.json` 的 condition-based 规则需迁移为 pattern-based
- `src/types/permission.py` 中的旧类型被移除
- 外部目录白名单机制保留，但放在用户规则之后检查

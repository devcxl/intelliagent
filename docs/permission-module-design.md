# 权限模块设计

## 概述

权限模块是一个自包含的独立包，提供 Agent 工具调用的权限检查、规则匹配和用户确认能力。支持 fnmatch 模式匹配的 last-match-wins 规则体系，以及工作区边界保护和外部目录白名单机制。

## 模块结构

```
src/permission/
├── __init__.py    # 统一公共 API 导出
├── types.py       # 类型定义：PermissionAction, Decision, PermissionCallback, Protocols
├── engine.py      # 权限引擎：PermissionEngine, load_permission_engine, 规则匹配
└── callback.py    # CLI 交互式权限确认：CliCallback
```

### 文件职责

| 文件 | 职责 | 公共导出 |
|------|------|----------|
| `types.py` | 枚举、数据模型、抽象基类、Protocol 契约 | `PermissionAction`, `Decision`, `PermissionCallback`, `PermissionEngineProtocol`, `PermissionCallbackProtocol` |
| `engine.py` | 规则匹配引擎、安全检查、工厂函数 | `PermissionEngine`, `load_permission_engine` |
| `callback.py` | CLI 交互式用户确认实现 | `CliCallback` |

## 数据流

一次权限检查请求的完整流程：

```
┌─────────────────────────────────────────────────────────────┐
│                       ReactEngine                           │
│                                                             │
│  1. 准备执行工具调用 (tool_name, args)                        │
│  2. 调用 permission_engine.check(tool_name, args)            │
│  3. 如果返回 ask，调用 permission_callback.on_prompt(...)     │
│  4. 根据 Decision.action 决定：允许 / 拒绝 / 等待用户确认      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    PermissionEngine.check()                  │
│                                                             │
│  ┌──────────┐    ┌──────────────┐    ┌───────────────┐      │
│  │ 用户规则  │───▶│ 安全检查      │───▶│ 默认规则       │      │
│  │(last-match)│   │ (路径越界)    │    │ (last-match)  │      │
│  └──────────┘    └──────────────┘    └───────────────┘      │
│                        │                                       │
│                        ▼                                       │
│                  ┌──────────────┐                              │
│                  │ 绝对兜底 ask  │                              │
│                  └──────────────┘                              │
│                                                             │
│  返回值: Decision(action, reason)                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          │                       │
          ▼                       ▼
   action=allow           action=ask
          │                       │
          ▼                       ▼
   执行工具调用          ┌──────────────────────┐
                        │  CliCallback          │
                        │  on_prompt()          │
                        │  → 用户输入 y/N       │
                        │  → 返回 bool          │
                        └──────────────────────┘
```

### 检查优先级（由高到低）

1. **用户规则** — last-match-wins 遍历 `self._rules`
2. **安全检查** — 路径越界且不在外部目录白名单 → `deny`
3. **默认规则** — last-match-wins 遍历 `_DEFAULT_RULES`
4. **绝对兜底** — 无匹配 → `ask`

## 规则匹配

### 模式匹配规则

`_match_rule(pattern, tool_name, args) → bool`：

1. **工具名匹配**：pattern 压缩空格后与工具名做 fnmatch
   - `"read *"` → `"read*"` → 匹配 `read_file`, `read_dir` 等
2. **参数值匹配**：原始 pattern 与每个字符串参数值做 fnmatch
   - `".env*"` → 匹配 args 中值为 `.env`、`.env.prod` 的参数

### Last-match-wins

```python
def _evaluate_rules(rules, tool_name, args):
    last_match = None
    for pattern, action in rules:
        if _match_rule(pattern, tool_name, args):
            last_match = (pattern, action)
    # 返回最后匹配的规则
```

规则列表末尾优先级最高，用户可在 `intelliagent.json` 中覆盖默认规则。

### 默认规则

| Pattern | Action | 说明 |
|---------|--------|------|
| `*` | ask | 全局兜底，所有未明确匹配的操作需确认 |
| `read *` | allow | 读操作自动放行 |
| `.env*` | deny | 禁止读取环境变量文件 |
| `skill *` | allow | skill 操作自动放行 |
| `edit *` | ask | 编辑操作需确认 |
| `bash *` | ask | shell 操作需确认 |
| `write *` | ask | 写操作需确认 |

## 配置模型

权限配置模型 `PermissionRule` / `PermissionsConfig` 定义在 `src/config/unified_config.py`，权限模块通过 `TYPE_CHECKING` 导入（运行时无依赖）：

```python
class PermissionRule(BaseModel):
    pattern: str = "*"
    action: Literal["allow", "ask", "deny"] = "ask"

class PermissionsConfig(BaseModel):
    rules: list[PermissionRule] = Field(default_factory=list)
    external_directories: list[str] = Field(default_factory=list)
```

### intelliagent.json 配置示例

```json
{
  "permissions": {
    "rules": [
      { "pattern": "read *", "action": "allow" },
      { "pattern": "write *", "action": "ask" },
      { "pattern": "bash *", "action": "ask" }
    ],
    "external_directories": [
      "/opt/shared/data"
    ]
  }
}
```

## 集成方式

### 运行时组装

`AgentRuntime` 通过工厂函数创建权限组件：

```python
# AgentRuntime._default_permission_engine_factory
from src.permission import load_permission_engine
return load_permission_engine(config.permissions, workspace=Path(config.workspace.dir))

# AgentRuntime._default_permission_callback_factory
from src.permission import CliCallback
return CliCallback(timeout=120.0)
```

### Protocol 契约

`PermissionEngineProtocol` 和 `PermissionCallbackProtocol` 定义在 `types.py` 中，`ReactEngine` 仅依赖 Protocol 而非具体实现，支持替换：

```python
class PermissionEngineProtocol(Protocol):
    def check(self, tool_name: str, args: dict[str, Any]) -> Decision: ...

class PermissionCallbackProtocol(Protocol):
    async def on_prompt(self, tool_name: str, args: dict[str, Any], reason: str) -> bool: ...
```

### 向后兼容

`src/types/__init__.py` 从 `src.permission` re-export 类型符号，旧导入路径 `from src.types import PermissionAction` 继续可用。

## 变更历史

- **2026-06-24**: 从 `src/types/permission.py`、`src/core/permission_engine.py`、`src/runtime/permission_callback.py` 收敛到 `src/permission/` 独立包。配置模型保留在 `src/config/unified_config.py`。

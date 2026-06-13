# 统一配置体系设计方案

## 研究结论摘要

现有配置分散在 `.env`、`permissions.json`、`mcp_config.json` 三个文件，使用两种不同的加载机制（Pydantic Settings 和手动 `json.load`），且 JSON 配置文件不支持环境变量引用。建议引入 **单一 `intelliagent.json` 配置文件 + 环境变量插值语法**，将现有所有配置收敛到一个文件中。

---

## 背景与问题定义

### 目标

将所有配置统一到单一 JSON 配置文件（类似 opencode 的 `opencode.json`），支持 `"{env:VAR_NAME}"` 语法从环境变量取值，消除分散配置的维护成本。

### 现状分析

| 配置来源 | 文件 | 加载方式 | 问题 |
|---------|------|---------|------|
| LLM 参数、数据库等 | `.env` / 环境变量 | Pydantic Settings | 隐式、无结构 |
| 权限规则 | `permissions.json` | 手动 `json.load` | 无验证、无插值 |
| MCP 服务器 | `mcp_config.json` | `MCPConfig.from_file()` | 有验证但无插值 |
| 工作区路径等 | `Settings` 类字段 | Pydantic Settings | 与 JSON 配置割裂 |

### 范围

- 合并 `permissions.json`、`mcp_config.json`、`.env` 中的配置项到统一文件
- 设计环境变量插值语法（参考 opencode 的 `"{env:OPENAI_API_KEY}"`）
- 不保持向后兼容（旧文件已废弃）
- 不改变已有配置的语义和默认值

### 限制

- 不引入新的外部依赖（已有 `pydantic-settings`、`pyyaml`）
- 不改动核心引擎逻辑，只改配置加载层
- 输出文档到 `docs/` 目录

---

## 关键发现

### 发现 1：Pydantic Settings 已提供了基础但不够

当前 `Settings` 类用 `pydantic-settings` 从环境变量和 `.env` 读取配置，这是合理的。问题是 JSON 配置文件完全没有纳入这个体系。两者各自独立加载，互不知道对方的存在。

### 发现 2：JSON 配置需要环境变量插值

用户提到的 `"{env:OPENAI_API_KEY}"` 语法是一种 **惰性求值标记**。在 JSON 加载时，遇到形如 `"{env:NAME}"` 的字符串，替换为 `os.environ.get("NAME", "")`。这需要在 JSON 加载层做一次后处理。

### 发现 3：配置文件需要 schema 验证

`permissions.json` 完全没有 schema 验证，加载失败直接 fallback 到默认值。用户可能写错字段而不知。统一配置文件应该用 Pydantic model 做完整校验。

### 发现 4：配置加载顺序应为：默认值 → JSON 文件 → 环境变量

合理优先级：**环境变量 > JSON 文件 > 代码默认值**。环境变量永远覆盖 JSON 文件，这符合 12-factor app 原则。JSON 文件中的 `"{env:XXX}"` 在文件加载阶段展开，但如果同名的真实环境变量在运行时存在，应该优先。

---

## 设计方案

### 核心思路

引入一个统一的配置模型 `UnifiedConfig`，所有配置项收敛到一个 `intelliagent.json` 文件。加载流程：

```
默认值 → intelliagent.json（含 {env:XXX} 插值） → 环境变量覆盖 → UnifiedConfig
```

### 环境变量插值语法

支持两种引用方式，与 opencode 对齐：

| 语法 | 行为 |
|------|------|
| `"{env:OPENAI_API_KEY}"` | 完整值替换为环境变量，空则报错 |
| `"{env:OPENAI_API_KEY:default_key}"` | 环境变量不存在时使用默认值 |

### 统一配置 JSON 结构

```jsonc
{
  // 顶层配置
  "llm": {
    "api_key": "{env:OPENAI_API_KEY}",
    "base_url": "{env:OPENAI_API_BASE}",
    "model": "{env:OPENAI_MODEL:gpt-4o-mini}",
    "reasoning_effort": "{env:OPENAI_REASONING_EFFORT}"
  },
  "workspace": {
    "dir": "{env:WORKSPACE_DIR:.}"
  },
  "database": {
    "url": "{env:DATABASE_URL:sqlite:///intelliagent.db}"
  },
  "experience_file": "{env:EXPERIENCE_FILE:experiences.json}",
  // 权限规则（合并 permissions.json）
  "permissions": {
    "rules": [
      {"tool": "run_shell", "action": "prompt", "conditions": {"dangerous": true}},
      {"tool": "run_shell", "action": "allow", "conditions": {}},
      {"tool": "read_file", "action": "allow", "conditions": {"path_in_workspace": true}},
      {"tool": "read_file", "action": "prompt", "conditions": {"path_in_workspace": false}},
      {"tool": "write_file", "action": "allow", "conditions": {"path_in_workspace": true}},
      {"tool": "write_file", "action": "prompt", "conditions": {"path_in_workspace": false}},
      {"tool": "edit_file", "action": "allow", "conditions": {"path_in_workspace": true}},
      {"tool": "edit_file", "action": "prompt", "conditions": {"path_in_workspace": false}},
      {"tool": "todo_write", "action": "allow", "conditions": {}}
    ]
  },
  // MCP 服务器配置（合并 mcp_config.json）
  "mcp": {
    "servers": [
      {
        "name": "filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "env": {}
      }
    ]
  }
}
```

### 模块设计

```
src/config/
├── __init__.py           # 导出 UnifiedConfig, get_config
├── settings.py           # 现有 Settings（保留向后兼容，或改为内部桥接）
├── unified_config.py     # 统一配置模型 + 加载逻辑
└── env_interpolator.py   # "{env:XXX}" 插值引擎
```

#### `env_interpolator.py`

```python
import os
import re

_ENV_PATTERN = re.compile(r'\{env:([^:}]+)(?::([^}]*))?\}')

def interpolate(value: str) -> str:
    """将字符串中的 {env:NAME} / {env:NAME:default} 替换为环境变量值。"""
    def _replace(m: re.Match) -> str:
        var = m.group(1)
        default = m.group(2)
        val = os.environ.get(var)
        if val is not None:
            return val
        if default is not None:
            return default
        raise ValueError(f"环境变量 {var} 未设置，且没有提供默认值")
    return _ENV_PATTERN.sub(_replace, value)

def deep_interpolate(obj: Any) -> Any:
    """递归遍历 JSON 结构，对所有字符串做插值。"""
    if isinstance(obj, str):
        return interpolate(obj)
    elif isinstance(obj, dict):
        return {k: deep_interpolate(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [deep_interpolate(v) for v in obj]
    return obj
```

#### `unified_config.py`

```python
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from src.config.env_interpolator import deep_interpolate


class LLMConfig(BaseModel):
    api_key: str = ""
    base_url: str | None = None
    model: str = "gpt-4o-mini"
    reasoning_effort: str | None = None


class WorkspaceConfig(BaseModel):
    dir: str = "."


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///intelliagent.db"


class PermissionRule(BaseModel):
    tool: str
    action: str = "prompt"
    conditions: dict[str, Any] = Field(default_factory=dict)


class PermissionsConfig(BaseModel):
    rules: list[PermissionRule] = Field(default_factory=list)


class UnifiedConfig(BaseModel):
    """统一配置模型 — 涵盖所有子配置域。"""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    experience_file: str = "experiences.json"
    permissions: PermissionsConfig = Field(default_factory=PermissionsConfig)
    mcp: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = "intelliagent.json") -> UnifiedConfig:
        path = Path(path)
        if not path.exists():
            return cls()  # 返回全默认值
        raw = json.loads(path.read_text(encoding="utf-8"))
        interpolated = deep_interpolate(raw)
        return cls.model_validate(interpolated)
```

### 向后兼容策略（已废弃）

旧配置文件（`.env`、`permissions.json`、`mcp_config.json`）已完全废弃，项目仅从 `intelliagent.json` 加载配置。

### 加载优先级

1. `intelliagent.json` 中的值（含 `{env:XXX}` 插值）
2. 真实环境变量覆盖（12-factor 优先）
3. 代码默认值

---

## 对比分析

| 维度 | 当前方案 | 统一方案 |
|------|---------|---------|
| 配置文件数 | 3+（.env, permissions.json, mcp_config.json） | 1（intelliagent.json） |
| 环境变量引用 | 仅 Pydantic Settings 支持 | 全 JSON 支持 |
| Schema 验证 | 仅 Settings（Pydantic）| 统一 Config 模型 |
| 配置发现 | 需读多处代码 | 读一个文件即了解全部 |
| 向后兼容 | — | 不保留，旧配置已废弃 |
| 新增配置项 | 至少改 2 个地方 | 改 1 个模型 + 1 个 JSON |

---

## 风险与不确定性

| 风险 | 说明 | 缓解措施 |
|------|------|---------|
| `permissions.json` 被用户直接编辑 | 已废弃，用户需迁移到 intelliagent.json | 删除旧文件，git rm 清理版本历史 |
| MCP 配置结构未来可能变化 | MCP 协议在演进 | `mcp` 字段用 `dict[str, Any]` 保持灵活 |
| `{env:XXX}` 在值中包含冒号 | 插值正则可能误匹配 | 用 `\{env:NAME:DEFAULT\}` 严格匹配，避免 URL 中的冒号干扰 |
| 性能影响 | 递归遍历 JSON 有开销 | 配置仅在启动时加载一次，开销可忽略 |

---

## 建议

### 实施步骤

1. **创建 `env_interpolator.py`** — 插值引擎，单元测试覆盖
2. **创建 `unified_config.py`** — 统一配置模型 + `load()` 方法
3. **更新 `Settings`** — 改为从 `UnifiedConfig` 构造（或直接替代）
4. **更新 `agent_runtime.py`** — 使用 `UnifiedConfig` 替代 `getattr(settings, ...)`
5. **更新 `load_permission_engine`** — 接受 `PermissionsConfig` 或保持兼容
6. **更新 `RunService._get_mcp_config`** — 从 `UnifiedConfig.mcp` 读取
7. **创建 `intelliagent.json.example`** — 模板文件
8. **编写迁移指南**

### 优先级建议

- **Phase 1**（核心）：`env_interpolator.py` + `unified_config.py` + 桥接旧 Settings
- **Phase 2**（接入）：更新 `agent_runtime.py`、`run_service.py` 消费新配置
- **Phase 3**（收尾）：`intelliagent.json.example`、迁移指南、测试

---

## 参考来源

- [opencode 配置文件](https://github.com/opencode-ai/opencode) — `{env:VAR}` 语法的设计参考
- [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — 当前项目使用的配置基础
- [12-Factor App: Config](https://12factor.net/config) — 环境变量优先原则
- 当前项目代码：`src/config/settings.py`、`src/core/permission_engine.py`、`src/mcp/config.py`

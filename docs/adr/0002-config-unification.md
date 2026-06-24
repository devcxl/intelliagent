# ADR 0002: 配置统一化

## 状态

已实施

## 背景

配置分散在三个文件（`.env`、`permissions.json`、`mcp_config.json`），使用两种加载机制（Pydantic Settings 和手动 `json.load`），且 JSON 文件不支持环境变量引用。主要问题：

- 新开发者需要阅读多处代码才能了解所有配置项
- 新增配置项需要改 2~3 个地方
- JSON 配置文件无 schema 验证，写错字段静默 fallback

## 决策

将所有配置收敛到单一 `intelliagent.json`，引入 `{env:VAR_NAME}` 语法支持环境变量引用。

## 详细设计

### 加载流程

```
默认值 → intelliagent.json（含 {env:XXX} 插值） → 环境变量覆盖 → UnifiedConfig
```

### 插值语法

| 语法 | 行为 |
|------|------|
| `"{env:VAR}"` | 替换为环境变量值，不存在则报错 |
| `"{env:VAR:default}"` | 环境变量不存在时使用默认值 |

### 模块结构

```
src/config/
├── env_interpolator.py    # 插值引擎：deep_interpolate() 递归遍历 JSON
├── unified_config.py      # UnifiedConfig Pydantic 模型 + load()
├── provider_config.py     # 提供商配置子模型
├── provider_registry.py   # 提供商注册表
└── settings.py            # 旧 Settings 桥接层（逐步淘汰）
```

### 配置优先级

1. 真实环境变量（12-factor app 原则）
2. `intelliagent.json`（含 `{env:XXX}` 展开后的值）
3. 代码默认值（Pydantic model defaults）

### 向后兼容

旧配置文件（`.env`、`permissions.json`、`mcp_config.json`）已完全废弃。项目仅从 `intelliagent.json` 加载配置。

## 理由

- **单文件发现**：读一个文件即了解所有配置
- **环境变量插值**：避免在 JSON 中硬编码 secrets
- **Pydantic 校验**：加载时即验证配置合法性
- **减少碎片**：配置文件数量从 3+ 降到 1

## 后果

- 用户需迁移旧配置到 `intelliagent.json`
- `settings.py` 保留为桥接层，待后续移除
- `mcp` 字段用 `dict[str, Any]` 保持灵活（MCP 协议仍在演进）

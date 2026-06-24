# 贡献指南

## 开发环境

```bash
uv sync --extra dev
```

## 代码规范

- Python 3.11+，类型标注全覆盖
- line-length=120，双引号
- 代码检查：`ruff check .`
- 格式检查：`ruff format --check .`

## 测试

```bash
uv run pytest --tb=short
```

测试策略：优先使用 monkeypatch 注入 fake 实现，避免真实 LLM/网络调用。

## 分支策略

- `main`：稳定分支，PR 合并目标
- PR 命名：`<type>/<short-description>`（如 `feat/agent-team-db-layer`）

## PR 流程

1. 确保 CI（lint + test）通过
2. PR 由 AI 审查 + 人工审查
3. 合并前需至少 1 个 approval

## 模块约定

- 新增工具注册在 `src/tools/registry.py`
- 新增配置项加在 `src/config/unified_config.py`
- 新增类型定义加在 `src/types/` 对应文件
- 重大决策记录到 `docs/adr/`

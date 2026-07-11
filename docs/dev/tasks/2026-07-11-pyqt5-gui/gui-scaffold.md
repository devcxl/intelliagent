---
name: "gui-scaffold"
depends_on: []
labels: ["gui"]
worktree_root: ".worktree/gui-scaffold/"
---

## 目标

搭建 GUI 模块的基础骨架：目录结构、依赖配置、空的入口文件。

## 实现要点

1. **pyproject.toml**: 添加 `[project.optional-dependencies] gui = [...]`（PyQt5, QFluentWidgets, qasync, mistune）
2. **目录结构**：创建 `src/gui/`、`src/gui/widgets/`、`src/gui/services/`、`src/gui/styles/`
3. **`__init__.py`**: 每个目录创建空 `__init__.py`
4. **`main.py`**: 创建最小骨架入口（`QApplication` + qasync + 占位主窗口）
5. **验证**: `uv sync --extra gui` 安装成功

## 验收标准

- [ ] `uv sync --extra gui` 成功后 PyQt5 可导入
- [ ] `python -m src.gui.main` 启动一个空白窗口（无崩溃）
- [ ] 目录结构完整

## Worktree
- 路径: `.worktree/gui-scaffold/`
- 分支: `feat/gui-scaffold`
- 创建时机: `/code` 阶段首次执行时自动创建
- 清理时机: PR 合并后自动删除

# IntelliAgent 项目文档

## 1. 项目概述
IntelliAgent 是一个基于 ReAct 架构的智能代理系统，旨在通过 Reason → Act → Observe 循环实现高效、可追溯的代码开发流程。系统结合 LLM 思考能力与工具执行能力，支持动态任务分解和自动化操作。

## 2. 核心架构
- **ReAct 循环引擎**：负责驱动整个任务流程，包括思考、行动、观察和迭代。
- **工具注册中心**：管理所有可用工具（如 `run_shell`, `read_file`, `write_file` 等），支持动态调用。
- **记忆管理器**：记录历史观察结果，确保任务连续性和上下文一致性。
- **上下文管理器**：维护当前任务的输入、状态和环境信息。

## 3. 关键组件
### Core 模块
- `react_engine.py`：实现 ReAct 循环核心逻辑，包括思考、行动、观察与迭代控制。
- `tool_registry.py`：工具注册与管理。
- `skill.py` 和 `skill_manager.py`：技能定义与调度。

### Skills 目录
当前存在两个技能目录：
- `84446078-98c0-4e3a-87b0-8026aec1dd83`
- `b7cc20a7-a1e2-4377-87ee-69ba88593e3d`

这些技能目录可能包含具体功能的实现，例如文件操作、代码生成等。

## 4. 已有文档列表
以下文档已存在于 `docs/` 目录中：
- `ANALYSIS_SUMMARY.md`
- `PDCA_OPTIMIZATION_PLAN.md`
- `QUICK_START.md`
- `REACT_ARCHITECTURE.md`
- `SKILL_GUIDE.md`
- `SKILL_IMPLEMENTATION_SUMMARY.md`
- `TOOLS.md`
- `TOOL_INTEGRATION.md`
- `WEB_UI.md`

## 5. 下一步建议
- 建议为每个技能目录添加具体功能说明文档。
- 可扩展 ReAct 引擎以支持更复杂的文档生成逻辑（如基于 LLM 自动生成内容）。
- 提供自动化文档生成脚本，用于在项目开发过程中持续更新文档。
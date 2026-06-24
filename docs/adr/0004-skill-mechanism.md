# ADR 0004: Skill 机制

## 状态

已实施

## 背景

IntelliAgent 需要一种按需加载专家指令的机制，让 LLM 在需要时获取特定领域的详细指引，而不必在每次对话中都注入所有指令。参考了 opencode 的 skill 系统和 Claude Code 的 hook 机制。

## 决策

采用三级渐进式 Skill 加载体系：元数据发现 → 按需加载 → 引用文件（预留），使用 YAML frontmatter + Markdown 正文格式。

## 详细设计

### Skill 文件格式

```markdown
---
name: my-skill
description: 用于 X 场景的专用指令
license: MIT
compatibility: opencode >= 1.0
metadata:
  category: devops
---

# Skill 正文

详细指令内容...
```

### 三级加载

1. **元数据发现**（启动时）：扫描路径，解析 YAML frontmatter，注册到 SkillRegistry
2. **按需加载**（运行时）：LLM 调用 `skill` 工具加载完整正文
3. **引用文件**（预留）：从 Skill 目录引用其他资源文件

### 模块结构

```
src/skills/
├── __init__.py
├── loader.py     Skill 文件发现与解析
├── model.py      数据模型（SkillDef, SkillFrontmatter）
├── registry.py   注册表（名称索引）
└── tool.py       skill 工具实现
```

### 扫描优先级

1. 项目级路径（`.agents/skills/`）— 同名时优先
2. 用户级路径（`~/.config/opencode/skills/`）

### 系统集成

- `AgentRuntime._load_skills()` 在构造函数中调用
- `ReactEngine._build_system_message()` 将 available_skills 注入 system prompt
- `skill` 工具注册到 `_default_registry`

## 理由

- **按需加载**：避免在 system prompt 中塞入大量指令，节省 token
- **渐进复杂度**：元数据足够小，可在每次对话中随 system prompt 注入；完整指令在需要时才加载
- **自包含**：每个 skill 是一个目录 + SKILL.md，可以 git 追踪、独立分发
- **与 opencode 兼容**：格式对齐 opencode skill，共享 skill 生态

## 后果

- 系统 prompt 需要额外 ~200 tokens 用于 available_skills XML
- 同名 skill 的项目级优先策略需文档说明
- 引用文件机制暂为预留，后续按需实现

# Claude Code 风格 Skill 系统指南

本指南说明如何在 IntelliAgent 中创建和使用 Claude Code 风格的 Skills。

## 概述

**Skill** 是一个自包含的可复用能力集合，支持多种功能执行和工作流定义。与传统的单文件实现不同，新的 Skill 系统采用 Claude Code 的目录结构和 Markdown 格式。

### 为什么使用 Skill？

1. **模块化** - 将功能组织成独立的、可复用的单元
2. **易于发现** - LLM 可以自动发现和推荐相关 Skills
3. **文档集成** - Markdown 格式便于版本控制和协作
4. **工作流支持** - 定义多步骤的复杂任务
5. **资源共享** - 每个 Skill 可以包含多个文档和资源文件

## 目录结构

Skill 采用标准的目录结构：

```
.claude/skills/
├── skill-name-1/
│   ├── SKILL.md          # Skill 定义和文档
│   ├── README.md         # 详细使用指南
│   └── *.md              # 其他资源文件
│
└── skill-name-2/
    ├── SKILL.md
    └── README.md
```

每个 Skill 是一个目录，包含：
- **SKILL.md** (必需) - 主定义文件，包含 YAML 前置和 Markdown 内容
- **README.md** (推荐) - 详细的使用指南和文档
- 其他 `.md` 文件 - 相关资源和文档

## 创建 Skill

### 1. 创建目录

```bash
mkdir -p .claude/skills/my-skill
cd .claude/skills/my-skill
```

目录名 (如 `my-skill`) 将成为 Skill 的 ID。

### 2. 创建 SKILL.md

**SKILL.md** 是 Skill 的主定义文件，包含两部分：

#### YAML 前置部分

```yaml
---
name: Skill 显示名称
description: Skill 的简洁描述
version: 1.0.0
author: 作者名
tags:
  - tag1
  - tag2
category: development
disable_model_invocation: false
---
```

**必需字段：**
- `name` - Skill 的显示名称
- `description` - Skill 的功能描述

**可选字段：**
- `version` - Skill 版本号（默认 1.0.0）
- `author` - 作者名（默认空）
- `tags` - 标签列表，用于搜索和分类
- `category` - Skill 分类（默认 "general"）
- `disable_model_invocation` - 是否禁止 LLM 自动调用（默认 false）

#### Markdown 内容部分

在 YAML 前置后面添加 Markdown 内容：

```markdown
# Skill 标题

Skill 的详细说明。

## Workflows

### Workflow 1
工作流描述

- 步骤 1
- 步骤 2

### Workflow 2
另一个工作流

- 步骤 A
- 步骤 B

## 主要功能

- 功能 1
- 功能 2

## 使用示例

示例代码或使用说明
```

### 3. 创建 README.md

创建详细的使用文档：

```markdown
# Skill 名称 - 详细指南

## 概述

关于 Skill 的详细说明

## 工作流说明

### Workflow 1

描述工作流 1 的目的和使用场景

- 耗时：估计耗时
- 适用场景：使用场景

### Workflow 2

...

## 配置参数

| 参数 | 类型 | 说明 |
|------|------|------|
| param1 | string | 参数 1 的说明 |
| param2 | integer | 参数 2 的说明 |

## 使用示例

```python
invoke_skill('skill-id', {
    'workflow': 'Workflow 1',
    'param1': 'value1'
})
```

## 常见问题

Q: 问题 1
A: 答案 1

...
```

## 完整示例

### 代码审查 Skill

**文件：.claude/skills/code-review/SKILL.md**

```markdown
---
name: Code Review Skill
description: 提供全面的代码审查，包括质量检查和最佳实践建议
version: 1.0.0
tags:
  - code-review
  - quality
category: development
---

# Code Review Skill

自动化的代码审查工具。

## Workflows

### Basic Review
快速代码风格检查

- 检查代码风格
- 验证命名规范

### Deep Analysis
深层代码分析

- 性能分析
- 复杂度计算
- 安全检查
```

**文件：.claude/skills/code-review/README.md**

```markdown
# Code Review Skill - 详细指南

## 概述

Code Review Skill 提供全面的代码审查功能...

## 工作流说明

### Basic Review

执行快速的代码质量检查...

### Deep Analysis

执行全面的代码分析...
```

## 使用 Skills

### 初始化

```python
from core.skill_integration import SkillIntegration

# 创建集成实例
integration = SkillIntegration()

# 初始化（加载所有 Skills）
integration.initialize()
```

### 查看可用 Skills

```python
# 获取所有可用 Skills 的描述（LLM 友好格式）
description = integration.get_available_skills_for_llm()
print(description)

# 按数量获取已加载的 Skills
count = integration.get_skill_count()
print(f"已加载 {count} 个 Skills")
```

### 推荐 Skills

```python
# 为任务推荐相关 Skills
recommendations = integration.suggest_skills_for_task(
    "分析代码质量",
    top_k=3
)

for rec in recommendations:
    print(f"推荐: {rec['name']}")
    print(f"描述: {rec['description']}")
```

### 调用 Skill

```python
# 调用 Skill
result = integration.invoke_skill('code-review', {
    'code': source_code,
    'workflow': 'Basic Review'
})

if result['success']:
    print(f"执行结果: {result['result']}")
else:
    print(f"错误: {result['error']}")
```

### 调用工作流

```python
# 调用 Skill 中的特定工作流
result = integration.invoke_workflow(
    skill_id='code-review',
    workflow_name='Deep Analysis',
    parameters={'code': source_code}
)
```

### 搜索 Skills

```python
# 搜索 Skills
results = integration.search_skills(
    query="documentation",
    tags=["api-docs"],
    category="documentation"
)

for skill in results:
    print(f"找到: {skill.metadata.name}")
```

### 查看执行历史

```python
# 获取执行历史
history = integration.get_execution_history(limit=10)

for record in history:
    print(f"Skill: {record['skill_name']}")
    print(f"结果: {'成功' if record['success'] else '失败'}")

# 获取统计信息
stats = integration.get_execution_stats()
print(f"成功率: {stats['success_rate']:.1%}")
```

## ReAct 引擎集成

Skill 集成与 ReAct 引擎无缝配合：

```python
from core.react_engine import ReActEngine
from core.skill_integration import SkillIntegration

# 创建 ReAct 引擎
engine = ReActEngine(llm_client=client)

# 创建 Skill 集成
skill_integration = SkillIntegration()
skill_integration.initialize()

# 将 Skills 作为工具提供给 ReAct
tools = skill_integration.get_skill_descriptions_for_tools()

# 在执行中使用
result = engine.execute(
    task="分析代码质量",
    available_tools=tools,
    skill_integration=skill_integration
)
```

## LLM 友好格式

Skills 为 LLM 生成专门格式的描述，便于 LLM 理解和使用：

```python
# 获取单个 Skill 的详细描述
description = integration.describe_skill_for_llm('code-review')

# 输出示例：
# **Skill: Code Review Skill**
# Description: 提供全面的代码审查...
# Tags: code-review, quality-assurance
# Category: development
# 
# **Available Workflows:**
# - Basic Review: 快速风格检查
# - Deep Analysis: 深层分析
```

## 最佳实践

### 1. 命名规范

- **Skill ID**：使用 kebab-case (如 `code-review`, `doc-generator`)
- **Workflow 名称**：使用 PascalCase (如 `BasicReview`, `DeepAnalysis`)
- **参数名**：使用 snake_case (如 `source_code`, `max_depth`)

### 2. 文档质量

- 为每个 Skill 提供详细的 README
- 清楚地说明每个 Workflow 的目的
- 提供实际的使用示例
- 列出所有参数和返回值

### 3. 工作流设计

- 每个 Workflow 应有明确的目标
- 步骤应该清晰且有序
- 避免过于复杂的 Workflow（超过 10 个步骤）

### 4. 版本管理

- 在 SKILL.md 中维护版本号
- 使用语义版本 (SemVer)：MAJOR.MINOR.PATCH
- 在 README 中记录重要变更

### 5. 标签和分类

- 合理使用标签便于搜索
- 选择合适的分类（development, documentation, testing 等）
- 避免过多标签（3-5 个最佳）

## 故障排除

### Skill 无法加载

```python
# 检查 Skills 目录
loader = SkillLoader()
skills = loader.load_all()

# 查看日志了解加载过程
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 工作流未被解析

- 确保 Workflows 部分使用 `## Workflows` 或 `## 工作流`
- 确保每个工作流使用 `### Workflow 名称` 格式
- 步骤必须以 `-` 或 `*` 开头

### LLM 无法找到 Skill

- 检查 `disable_model_invocation` 是否设为 `false`
- 确保 Skill 已正确加载（检查加载日志）
- 检查 Skill 的描述是否清晰明确

## 迁移指南

从旧的 Skill 系统迁移到新系统：

### 旧系统 → 新系统

**旧的 JSON 格式：**
```json
{
  "id": "skill-1",
  "name": "Skill 1",
  "metadata": {...},
  "code": "..."
}
```

**新的 Markdown 格式：**
```
.claude/skills/skill-1/
├── SKILL.md
└── README.md
```

**迁移步骤：**

1. 为每个 Skill 创建目录
2. 从元数据创建 YAML 前置
3. 从代码文档创建 Markdown 内容
4. 从类型信息导出 Workflows
5. 转换配置参数为 Markdown 表格

## 常见问题

**Q: 可以在 Skill 中执行 Python 代码吗？**
A: 可以。Skill 定义是 Markdown 格式，但执行逻辑可以通过外部工具或脚本实现。

**Q: 支持嵌套的工作流吗？**
A: 目前不支持嵌套。可以通过在同一 Skill 中定义多个 Workflow 或创建相关的 Skills 实现。

**Q: 可以共享资源文件吗？**
A: 可以。每个 Skill 可以有多个 `.md` 文件，可以通过 `get_resource()` 方法访问。

**Q: 如何禁止 LLM 自动调用某个 Skill？**
A: 在 SKILL.md 的 YAML 中设置 `disable_model_invocation: true`。

**Q: Skill 可以调用其他 Skill 吗？**
A: 可以，通过在工作流中引用其他 Skill 的 ID 实现。

## 相关链接

- [Claude Code 官方文档](https://code.claude.com/docs)
- [ReAct 引擎文档](./REACT_ENGINE.md)
- [API 参考](./API_REFERENCE.md)

## 发展路线

未来版本计划：

- ✅ 基础 Markdown 解析
- ✅ 工作流定义和执行
- ⏳ 动态参数绑定
- ⏳ Skill 版本管理
- ⏳ 权限控制
- ⏳ Skill 市场和共享

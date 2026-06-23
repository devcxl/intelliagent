## Agent Brief

**类别：** enhancement
**摘要：** 实现三级渐进式 Skill 加载系统——启动时发现 skills 元数据（Layer 1），模型通过内置 `skill` 工具按需激活完整指令（Layer 2），为后续引用文件加载（Layer 3）预留接口。

**当前行为：**

- `ReactEngine.run()` 使用固定的 `DEFAULT_SYSTEM_PROMPT`（`src/core/constants.py`），无 skills 注入能力
- `ToolRegistry` 管理 `run_shell`、`read_file`、`write_file`、`edit_file`、`todo_write` 五个内置工具，无 `skill` 工具
- `UnifiedConfig` 涵盖 `model`、`provider`、`workspace`、`database`、`permissions`、`mcp` 六个配置域，无 skills 配置
- `AgentRuntime.create_engine()` 组装 ReactEngine，但不加载 skills
- `PermissionEngine` 基于 fnmatch 的 last-match-wins 规则匹配，无 skill 专用权限语义

**期望行为：**

### 1. Skill 文件格式

每个 Skill 是 `{skill_name}/SKILL.md` 目录结构。`SKILL.md` 包含 YAML frontmatter 和 Markdown body：

```yaml
---
name: my-skill
description: 一句话描述（约80 tokens），仅在 Layer 1 展示给模型
license: MIT
compatibility: opencode
metadata:
  tags: ["python", "testing"]
---
# 指令正文
## 使用场景
...
```

- `name` 和 `description` 为必填字段
- YAML 解析失败时跳过该 skill（不中断启动），记录 WARNING 日志
- body 为 skill 的完整指令文本，仅当模型调用 `skill` 工具后才注入
- 同名 skill（从不同路径发现）时，项目级 `.agents/skills/` 优先于用户级 `~/.config/opencode/skills/`

### 2. SkillLoader — 发现与解析

- 扫描路径：`.agents/skills/`（项目级）和 `~/.config/opencode/skills/`（用户级）
- 递归遍历子目录，找到所有 `SKILL.md` 文件
- 解析每个 `SKILL.md` 的 YAML frontmatter（`---` 分隔符之间的内容）和 body
- 返回 `list[SkillDef]`，按优先级排序（项目级在前）
- 扫描目录不存在时静默跳过（不是错误）
- 空 skills 目录时返回空列表（不是错误）

### 3. SkillDef 数据模型

```python
class SkillFrontmatter(BaseModel):
    name: str           # 唯一标识
    description: str    # 简短描述（Layer 1 展示）
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class SkillDef(BaseModel):
    frontmatter: SkillFrontmatter
    body: str           # frontmatter 之后的全部 Markdown 内容
    source_path: Path   # SKILL.md 所在目录的绝对路径（用于 Layer 3 引用文件）
```

### 4. SkillRegistry — 注册表

- 持有 `dict[str, SkillDef]`（key 为 `name`）
- `register(skill: SkillDef) -> None` — 注册单个 skill，同名时后注册的被忽略（项目级优先策略由 SkillLoader 保证顺序）
- `get(name: str) -> SkillDef | None` — 按名称查找
- `generate_available_skills_xml() -> str` — 生成 `<available_skills>` XML 块，仅包含 name + description，格式：

```xml
<available_skills>
  <skill>
    <name>my-skill</name>
    <description>一句话描述</description>
  </skill>
</available_skills>
```

- `list_names() -> list[str]` — 列出所有已注册 skill 名称

### 5. `skill` 内置工具

注册到 `_default_registry`，名称为 `skill`：

- 参数：`name: str`（必填，skill 名称）
- 行为：从 `SkillRegistry` 查找 `name`，返回 `SkillDef.body` 全文
- skill 不存在时返回错误 JSON：`{"status": "error", "error": "未知 skill: {name}", "code": "UNKNOWN_SKILL"}`
- 工具描述应引导模型理解：调用此工具加载 skill 的完整指令后，模型应遵循其中的指示行事

### 6. System Prompt 注入

`ReactEngine.run()` 和 `iter_steps()` 构建 system message 时：

1. 基础 system prompt：`DEFAULT_SYSTEM_PROMPT`（现有）
2. 追加 available_skills XML 块（由 SkillRegistry 生成）
3. 追加一段简短说明引导模型何时使用 `skill` 工具

生成后的 system prompt 结构：
```
{基础 system prompt}

<available_skills>
{SkillRegistry 生成的 XML}
</available_skills>

当任务匹配某个 skill 的描述时，使用 skill 工具加载其完整指令。
```

### 7. SkillsConfig — 配置模型

在 `UnifiedConfig` 中新增 `skills` 字段：

```python
class SkillsConfig(BaseModel):
    enabled: bool = True              # 是否启用 skills 功能
    project_paths: list[str] = Field(  # 项目级扫描路径
        default_factory=lambda: [".agents/skills"]
    )
    user_paths: list[str] = Field(    # 用户级扫描路径
        default_factory=lambda: ["~/.config/opencode/skills"]
    )

class UnifiedConfig(BaseModel):
    # ... 现有字段 ...
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
```

### 8. PermissionEngine 集成

`skill` 工具不执行副作用（不读写文件、不执行命令），默认规则应设为 `allow`。在 `_DEFAULT_RULES` 中新增：

```python
("skill *", "allow"),
```

该规则放在 `("*", "ask")` 之前（`skill *` 更具体，先匹配），无需用户确认。

### 9. AgentRuntime 集成

`AgentRuntime` 在构造时加载 skills，传递给 `ReactEngine`：

- `AgentRuntime.__init__()` 中：`SkillsConfig.enabled == True` 时，调用 `SkillLoader` 发现并解析 skills → 注册到 `SkillRegistry`
- `create_engine()` 中：将 `SkillRegistry` 实例传入 `ReactEngine` 构造函数
- 向 `_default_registry` 注册 `skill` 工具（如果尚未注册）

`ReactEngine` 新增可选参数：

```python
def __init__(
    self,
    # ... 现有参数 ...
    skill_registry: SkillRegistry | None = None,
):
```

### 10. 错误处理

| 场景 | 行为 |
|------|------|
| SKILL.md 无 YAML frontmatter | 跳过该 skill，WARNING 日志 |
| YAML frontmatter 缺少 name | 跳过该 skill，WARNING 日志 |
| YAML frontmatter 缺少 description | 跳过该 skill，WARNING 日志 |
| 扫描目录不存在 | 静默跳过（DEBUG 日志） |
| 模型调用不存在的 skill | `skill` 工具返回错误 JSON |
| `skills.enabled = false` | 完全跳过 skill 加载，不注入 XML，不注册 `skill` 工具 |

**关键接口：**

- `SkillFrontmatter` — Pydantic 模型，YAML frontmatter 的结构化表示
- `SkillDef` — Pydantic 模型，完整 skill 定义（frontmatter + body + source_path）
- `SkillLoader.load(project_paths: list[Path], user_paths: list[Path]) -> list[SkillDef]` — 从文件系统发现并解析 SKILL.md
- `SkillRegistry` — 注册表类，管理 SkillDef 集合，生成 available_skills XML
- `skill_tool(name: str) -> str` — 内置工具函数，按名称查找并返回 skill body
- `SkillsConfig` — 配置模型，控制 skills 扫描路径和启用/禁用
- `ReactEngine.__init__(skill_registry=...)` — 新增可选参数，用于注入 skill 到 system prompt

**验收标准：**

- [ ] `SkillLoader.load()` 能从 `.agents/skills/` 和 `~/.config/opencode/skills/` 递归发现所有 `SKILL.md` 文件
- [ ] YAML frontmatter 正确解析，缺少 name 或 description 时跳过该 skill（不中断加载），记录 WARNING
- [ ] 同名 skill 冲突时项目级优先于用户级（先注册的保留）
- [ ] `SkillRegistry.generate_available_skills_xml()` 输出格式正确的 XML 块
- [ ] `skill` 工具注册到 `_default_registry`，模型调用 `skill({name: "xxx"})` 返回完整 body
- [ ] `ReactEngine.run()` 构建的 system message 包含 available_skills XML 块
- [ ] `skills.enabled = false` 时完全跳过 skill 加载，不影响现有行为
- [ ] `skill` 工具的权限默认为 `allow`（在 `_DEFAULT_RULES` 中）
- [ ] 所有现有测试无回归（`pytest tests/` 全部通过）
- [ ] 新增单元测试覆盖 SkillLoader、SkillRegistry、`skill` 工具函数
- [ ] 新增集成测试覆盖从配置加载到 system prompt 注入的完整链路

**不在范围内：**

- Layer 3 — references 目录下的文件按需加载（`SkillDef.source_path` 已预留路径，后续迭代实现）
- Skill 市场 / 远程分发 / 版本管理
- 运行时 Skill 热更新（需要重启或重建 AgentRuntime 才能加载新 skill）
- `metadata` 字段的语义解析（当前仅存储，不做任何解释）
- `license` 和 `compatibility` 字段的校验逻辑

# IntelliAgent

基于投影式压缩引擎的插件化编码智能体框架。受 Claude Code、Codex、OpenCode 与 pi（badlogic/pi-mono）启发，强调**可解释性**、**插件化能力面**和**架构即产出**。

> **安全提示（ADR 0008）**：发行版不捆绑 permission 插件——未安装 permission 插件时，所有工具调用（含 bash）**不经确认直接执行**。面向不可信任务使用前，请先安装 permission 插件。

## 架构

```
src/
├── core/         Engine（双层循环状态机）+ 插件宿主（PluginHost）+ 工具流水线 + 投影式压缩
├── plugins/      内置插件：basic_tools（read/write/bash/edit/grep）、mcp、skill、storage
├── llm/          流协议、LLM 编排层（重试/abort/usage）与协议适配器
├── config/       YAML 配置（intelliagent.yaml + {env:VAR} 插值）
├── runtime/      组合根（plugin_assembly：配置 → PluginHost → Engine）
├── tui/          Textual TUI（消息流 + 流式渲染 + 工具折叠）
└── headless/     无头模式（CLI 任务进、JSON Lines 事件出）
```

**核心数据流**：`TUI/Headless → Engine → LLM ProviderClient/Adapter → ToolPipeline → PluginHost(Capability) → Storage`

**插件契约**（ADR 0007）：Manifest + Plugin Protocol，Entry Points 是第三方插件的唯一发现入口，内置插件走同一契约。能力类型：tool / hook / permission / storage——一个插件可注册多种能力。memory、permission 等由外部插件承载。

**引擎**（ADR 0010，复刻 pi）：双层循环状态机、stopReason 三分类、steering/follow-up 插话、turn 边界 hooks、投影式压缩（原始记录永不删除，上下文每次请求现算）。

## 快速开始

```bash
# 安装依赖
uv sync --extra dev

# 配置（字段与注释见示例文件）
cp intelliagent.yaml.example intelliagent.yaml
```

环境变量插值：`"{env:OPENAI_API_KEY}"` / `"{env:VAR:default}"`（引号必须保留）。

### Provider 与自定义端点

配置以 provider 为中心：`default_model` 选择模型，`providers` 声明线协议、端点、密钥来源与模型清单。

```yaml
default_model: deepseek/deepseek-flash

providers:
  deepseek:
    type: openai-compatible
    api: https://api.deepseek.com
    env: [DEEPSEEK_API_KEY]
    models:
      deepseek-flash:
        id: deepseek-flash
        limit:
          context: 1048576
          output: 393216
```

- `type` 决定线协议：`openai-compatible` 走 Chat Completions，`openai` 走 Responses（`/v1/responses`），`anthropic` 走 Messages（`/v1/messages`）。
- `env` 按顺序取第一个非空环境变量；`openai` 缺省 `OPENAI_API_KEY`，`anthropic` 缺省 `ANTHROPIC_API_KEY`；`openai-compatible` 留空表示不带鉴权。
- 密钥只从环境变量读取，不写进 YAML；`default_model` 的 provider/model 与密钥在启动时校验。
- `models` 的键是 Model Ref 的第二段，`id` 缺省等于键并作为线上模型名。
- `limit.output` 作为请求未指定时的默认输出上限；`tool_call: false` 时请求不下发工具。
- `reasoning` / `cost` / `modalities` 等元数据可声明，当前不产生行为（示例文件中标注为「仅声明」）。

```yaml
providers:
  openai:
    type: openai              # Responses；api/env 可省略，使用官方缺省
    models:
      gpt-5: {}
  anthropic:
    type: anthropic           # Messages
    models:
      claude-sonnet-4-5: {}
```

端点需支持所选协议的流式响应与 function calling；Agent 依赖工具调用，
不支持工具的模型需把 `tool_call` 设为 `false` 才能纯聊天。usage 建议回传（缺失时该响应记为 None）。

### 无头模式（脚本化）

```bash
# 任务参数进、JSON Lines 事件流出
uv run intelliagent run "读取 README.md 并总结"

# stdin 进
echo "任务" | uv run intelliagent run

# 免安装形态
uv run python -m src.headless run "任务"
```

退出码：`0` 成功收束（settled/terminated）、`1` 运行失败/中止、`2` 启动失败。

### TUI（交互式）

```bash
uv run python -m src.tui
```

消息流 + 流式增量渲染 + 工具调用折叠 + 多行编辑器（ctrl+j 提交）+ 状态栏。

## 插件开发

第三方插件经 Entry Points 发现（group `intelliagent.plugins`）：

```python
# my_plugin.py
from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, Manifest

class MyPlugin:
    manifest = Manifest(
        name="my-plugin", version="0.1.0", api_version=1,
        capabilities=(CapabilityDeclaration(kind=CapabilityKind.TOOL, name="my.tool"),),
        config_schema=MyConfig,  # 可选：pydantic 配置 schema
    )

    def register(self, registrar, config):
        registrar.register(CapabilityKind.TOOL, "my.tool", my_tool_provider)
```

```toml
# pyproject.toml
[project.entry-points."intelliagent.plugins"]
my-plugin = "my_plugin:MyPlugin"
```

Hook 能力（beforeToolCall/afterToolCall/turn 边界）可实现 permission、memory 等外部插件——内核不捆绑实现（ADR 0008）。

## 内置工具

| 工具 | 说明 |
|------|------|
| `read` | 分页读取（offset/limit + 续读提示，输出限额） |
| `write` | 写文件（只返回成功消息，不回灌内容） |
| `bash` | 命令执行（进程组 kill、输出落盘 offload、超时封顶） |
| `edit` | 精确匹配编辑（返回 diff，多匹配需显式策略） |
| `grep` | ripgrep 检索（匹配数/行宽限额，缺依赖可诊断） |

## 测试

```bash
uv run pytest --tb=short
uv run ruff check . && uv run ruff format --check .
```

测试策略：fake 注入（FakeLLM、fake 插件），不触网；真实 LLM 路径 opt-in（`pytest -m integration` + `OPENAI_API_KEY`）。

## 模块职责

| 模块 | 职责 |
|------|------|
| `src/core/` | 引擎循环、插件宿主、工具流水线、压缩。无 provider 细节，无持久化实现。 |
| `src/plugins/` | 内置插件（能力实现）。与外部插件走同一契约。 |
| `src/llm/` | 流协议、编排层（重试/abort/usage）与协议适配器。无 agent 循环策略。 |
| `src/runtime/` | 组合根：配置 → PluginHost → Engine。 |
| `src/config/` | YAML 配置读取。无业务逻辑。 |
| `src/tui/` / `src/headless/` | 前端，仅消费引擎事件流。 |

## License

MIT

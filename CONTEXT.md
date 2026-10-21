# IntelliAgent Context Map

## 项目定位

IntelliAgent 是一个**编码 Agent 框架**（非 Web 应用），核心目标不是功能完备，而是**可解释的架构**——每个模块的职责用一句话能讲清楚，适合教学与展示。当前处于插件化重构期（见 `docs/2026-10-21-plugin-refactor-plan.md`）。

## Language

### 内核

**Run**:
一次完整的 agent 执行：从接收任务到产出最终回答。
_Avoid_: Session run, execution session

**Conversation**:
多轮对话，包含多条 Message。
_Avoid_: Chat, thread

**Message**:
Conversation 中的一条记录：用户输入、助手回复、工具调用或工具结果。
_Avoid_: Event, entry

**Tool**:
可被模型调用的能力单元，有 schema 与执行函数。
_Avoid_: Function, action

**Observation**:
一次工具执行的结果记录。
_Avoid_: Tool output, result message

**Engine**:
驱动推理-行动循环（ReAct）的核心，消费模型响应并执行工具调用。
_Avoid_: Loop, orchestrator, core loop

**Projection**:
发给模型的上下文视图，每次请求时从 append-only 记录现算；历史记录永不删除，只决定哪些进入视图。
_Avoid_: Context buffer, history window

**Compaction**:
追加一条摘要记录（含保留切点）以缩小投影的机制，不修改也不删除原始记录。
_Avoid_: Truncation, pruning, history deletion

**Entry**:
存储层的统一记录单元（message/compaction/run 等），append-only，以 parent 链接成树。仅用于存储语境；消息语境仍称 Message。
_Avoid_: Row, record

### 插件体系

**Plugin**:
通过 Manifest 声明能力并经注册表加载的扩展单元；内置插件与外部插件走同一契约。
_Avoid_: Extension, module, addon

**Built-in Plugin**:
随发行版捆绑的插件（基本工具、MCP、Skill、存储）。
_Avoid_: Core plugin, native plugin

**External Plugin**:
由第三方提供、经 Entry Points 发现的插件（如 memory）。
_Avoid_: Community plugin, third-party module

**Capability**:
插件可注册的能力类型（tool / hook / permission / storage）；一个插件可注册多种能力。
_Avoid_: Interface, provider type

**Manifest**:
插件的声明式描述：名称、版本、API 版本、能力与配置 schema。
_Avoid_: Plugin config, descriptor

**Entry Point**:
外部插件的唯一发现入口。
_Avoid_: Plugin registry, loader path

**Hook**:
引擎生命周期上的挂载点，插件可在其上注入上下文或拦截行为。
_Avoid_: Callback, interceptor

**Permission**:
工具调用的放行策略，由 permission 能力的插件提供；发行版不捆绑实现。
_Avoid_: Access control, approval

**Memory**:
跨会话的知识积累，由外部插件实现；内核不内置记忆策略。
_Avoid_: Knowledge base, context store

**Skill**:
按需加载的专家指令集，YAML frontmatter + Markdown 正文。
_Avoid_: Prompt template, playbook

**MCP**:
Model Context Protocol，外部工具服务器的标准接入方式。
_Avoid_: Tool server, external tools

### 前端

**TUI**:
基于 Textual 的终端界面，唯一交互式前端。
_Avoid_: GUI, UI layer

**Headless Mode**:
无交互界面的执行入口：一次性任务参数或 stdin 进入，事件流出，供脚本与测试使用。
_Avoid_: CLI mode, batch mode

## 架构分层（目标态）

```
src/
├── core/        Engine、hook 管线、插件宿主（PluginHost）。无 provider 细节，无持久化所有权
├── plugins/     内置插件：read/write/bash/edit/grep、mcp、skill、storage
├── llm/         litellm 统一接入
├── config/      YAML 配置读取
├── tui/         Textual 界面
└── headless/    无头执行入口
```

**核心数据流**：`TUI/Headless → Engine → LLM(litellm) → PluginHost(Capability) → Storage`

## 设计原则

- **KISS/YAGNI**：不做过度设计，不写用不到的代码
- **一切能力皆插件**：内核只保留 Engine 与插件宿主；能力缺失即功能缺失，不设隐式默认
- **显式数据流**：避免全局状态，依赖通过构造函数注入
- **删除胜过兼容**：重构中淘汰的实现直接删除，不留兼容层

## 技术栈

- Python 3.11+、litellm、pydantic、sqlalchemy、aiosqlite、textual、mcp、pytest
- 依赖管理：uv
- 代码风格：ruff (line-length=120, double quotes)

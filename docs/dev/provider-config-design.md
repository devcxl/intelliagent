# Provider 配置与原生协议适配器设计

关联：ADR 0011（决策）、ADR 0009（YAML 配置）、ADR 0010（pi 引擎）。

## 目标

- 配置以 provider 为中心，一个文件描述多个 provider、端点、凭证来源与模型清单。
- 三种线协议由显式适配器承载：`openai`（Responses）、`openai-compatible`（Chat Completions）、`anthropic`（Messages）。
- 删除 litellm；`LLMClient` 的流协议、错误进流、重试与 usage 账本纪律不变。
- 引擎与 core 仍然只认 `provider/model-id` 字符串，不感知协议、端点与密钥。

## 非目标

- 不做模型自动发现、模型选择器或 `models.dev` 目录同步。
- 不做 provider 级 `headers` / `body` 覆盖（后续按需加）。
- 不接线 Compactor；`limit.context` 本次只声明。
- 不实现 reasoning 流事件、成本账、多模态与结构化输出。
- 不支持 Bedrock / Vertex 等非 OpenAI/Anthropic 原生协议。

## 术语

| 术语 | 定义 |
|---|---|
| Provider | 一套模型来源：线协议、API 端点与凭证的组合。 |
| Protocol | 与 Provider 通信的线协议：`openai` / `openai-compatible` / `anthropic`。 |
| Model | Provider 下的一个可调用模型条目：线上模型名、能力与限额。 |
| Model Ref | `provider/model-id` 字符串，引擎与请求层唯一使用的模型标识。 |
| Model Target | Model Ref 的运行时解析结果（协议、端点、密钥、限额）；仅 llm 层内部使用。 |

## 配置 schema

```yaml
default_model: deepseek/deepseek-flash

providers:
  deepseek:
    type: openai-compatible
    api: https://api.deepseek.com
    env: [DEEPSEEK_API_KEY]
    name: DeepSeek
    models:
      deepseek-flash:
        id: deepseek-flash
        name: DeepSeek V4.1 Flash 1017
        description: "October 17 update of DeepSeek V4.1 Flash"
        attachment: true
        reasoning: true
        reasoning_level: [low, high, max]
        tool_call: true
        interleaved:
          field: reasoning_content
        structured_output: true
        temperature: true
        modalities:
          input: [text, image]
          output: [text]
        limit:
          context: 1048576
          output: 393216
        cost:
          input: 0.15
          output: 0.6
          reasoning: 0.6
          cache_read: 0.003

workspace:
  dir: "."

plugins:
  basic-tools:
    enabled: true
  storage:
    enabled: true
    config:
      database_url: "sqlite:///intelliagent.db"
```

### Provider 字段

| 字段 | 必填 | 语义 |
|---|---|---|
| `type` | 是 | `openai` / `openai-compatible` / `anthropic`，决定线协议。 |
| `api` | 视类型 | 原样作为 SDK 的 `base_url`，不自动补 `/v1`。`openai` 缺省 `https://api.openai.com/v1`，`anthropic` 缺省 `https://api.anthropic.com`；`openai-compatible` 必填。 |
| `env` | 否 | 有序环境变量名；取第一个非空值为 API Key。缺省：`openai` → `OPENAI_API_KEY`，`anthropic` → `ANTHROPIC_API_KEY`，`openai-compatible` 无缺省（留空表示不要求密钥；适配器发送占位 Authorization，端点应忽略鉴权）。YAML 不接受明文 key。 |
| `name` | 否 | 展示名，供 TUI/文档使用。 |
| `models` | 是 | 模型条目表，键是 Model Ref 的第二段。 |

### Model 字段

| 字段 | 必填 | 语义 | 本次是否消费 |
|---|---|---|---|
| `id` | 否 | 发给上游的模型名；缺省等于条目键。 | 是 |
| `name` | 否 | 展示名。 | 仅展示 |
| `description` | 否 | 模型说明。 | 仅展示 |
| `limit.context` | 否 | 上下文上限（token）。 | 声明；Compactor 接线后消费 |
| `limit.output` | 否 | 输出上限（token）。 | 是：`request.max_tokens` 为空时作为默认值 |
| `tool_call` | 否 | 是否支持 function calling；缺省 `true`。 | 是：`false` 时不下发 tools |
| `temperature` | 否 | 是否接受 temperature 参数；缺省 `true`。 | 声明；温度配置落地后消费 |
| `attachment` / `modalities` / `structured_output` | 否 | 多模态与结构化输出能力。 | 仅声明 |
| `reasoning` / `reasoning_level` / `interleaved` | 否 | 思考过程与交错字段能力。 | 仅声明 |
| `cost` | 否 | 每百万 token 单价（input/output/reasoning/cache_read）。 | 仅声明 |

`reasoning`、`cost`、`modalities`、`attachment`、`structured_output`、`temperature` 在 schema 中可写，但当前不产生任何行为；README 与示例文件必须标注「仅声明」，避免重演 `max_steps` 的静默失效。

### 校验与启动错误

- `default_model` 必填，按第一个 `/` 切分为 provider 与 model-id；模型 id 内的 `/` 保留。
- provider 必须存在、model 条目必须存在；错误信息带配置路径（沿用 `ConfigError` 风格）。
- 启动时只解析 `default_model` 引用的 provider 并检查其密钥；其余 provider 懒解析，避免未使用的 provider 阻塞启动。
- 若 YAML 仍含旧 `model:` 字段，报错并提示改为 `default_model` + `providers`（不复用 pydantic 的笼统 extra 报错）。
- provider 类型与 `api` 的组合非法（如 `openai-compatible` 缺 `api`）在配置层拒绝。

## 数据流与模块边界

```
intelliagent.yaml
      │ load_config（src/config）
      ▼
IntelliAgentConfig ── runtime 装配（plugin_assembly / tui.assembly / headless.cli）
      │                         │
      │                         ├─ build_host(config)
      │                         └─ ModelRegistry.from_config(config.providers)
      ▼                                   │
Engine(model="deepseek/deepseek-flash") ◄─┘
      │ StreamRequest(model="deepseek/deepseek-flash")
      ▼
ProviderClient（重试、abort、usage 账本）
      │ target = registry.resolve(request.model)
      ▼
ProtocolAdapter.stream(target, request, abort) -> Iterator[LLMEvent]
```

- 配置模型（pydantic）留在 `src/config/providers.py`；运行时转换在组合根完成，`src/llm` 只接收 `ProviderSettings` / `ModelSettings` 或等价的不可变 dataclass，避免 llm 依赖配置层。
- `Engine`、`turn_hooks`、`token_counting` 不改：模型仍是字符串，压缩/钩子切换模型（`NextTurnUpdate.model`）时按新 ref 逐请求解析。

## 模块布局

```
src/config/providers.py          # Protocol、ProviderConfig、ModelConfig、Limits、Cost、Modalities、Interleaved
src/llm/provider_registry.py     # ModelTarget、ModelRegistry.resolve()
src/llm/client.py                # ProviderClient：resolve → adapter → 重试/abort/usage
src/llm/errors.py                # ProviderError（retryable 标记）
src/llm/protocols/openai_chat.py
src/llm/protocols/openai_responses.py
src/llm/protocols/anthropic_messages.py
```

删除：`src/llm/litellm_client.py`、`_skip_mcp_handler` 补丁；`pyproject.toml` 移除 `litellm`，新增 `anthropic`。

## 适配器契约

```python
class ProtocolAdapter(Protocol):
    def stream(self, target: ModelTarget, request: StreamRequest, abort: threading.Event | None) -> Iterator[LLMEvent]: ...
```

- 适配器只做「请求投影 + 流事件翻译 + 错误分类」，不重试、不记账、不写事件出口。
- abort 的置位由调用方/编排层决定；流内响应（尽快收束、释放连接、携带已消耗的 usage）由适配器执行——usage 与连接是传输事实，适配器是唯一知情者。编排层保留 pre-stream abort 与重试决策。
- SDK 客户端：`OpenAI(max_retries=0, timeout=...)`、`Anthropic(max_retries=0, timeout=...)`；超时值由 `ProviderClient` 传入。
- SDK 异常在适配器内映射为 `ProviderError(message, retryable=...)`。`ProviderClient` 只捕获 `ProviderError`；其他异常原样抛出（编程错误不得伪装成模型错误）。
- 适配器必须关闭 SDK 流（上下文管理器 / `finally`），保证 abort 或错误后连接释放。
- `Done` 恰好一个；`Error` 先于 `Done`；abort 时尽快产出 `Done("aborted")`。

## 三协议映射

### 请求投影

| 内部 | openai-compatible | openai（Responses） | anthropic |
|---|---|---|---|
| system 消息 | 原样 `role=system` | 提升为 `instructions` | 合并为顶层 `system` |
| user/assistant 文本 | 原样 | `input` 消息项 | `content` 文本块 |
| assistant `tool_calls` | 原样 | `function_call` item（`call_id`/`name`/`arguments`） | `tool_use` block（`input` 为解析后的对象） |
| `role=tool` 结果 | 原样 | `function_call_output` item | user 消息中的 `tool_result` block |
| tools schema | `{type:function, function:{...}}` | `{type:function, name, description, parameters}` | `{name, description, input_schema}` |
| 输出上限 | `max_tokens` | `max_output_tokens` | `max_tokens`（必填；缺省取 `limit.output`，再无则 4096） |
| temperature | 透传 | 透传 | 透传（仅 `temperature != None`） |

### 流事件与收束

| 事件 | openai-compatible | openai（Responses） | anthropic |
|---|---|---|---|
| 文本增量 | `choices[].delta.content` | `response.output_text.delta` | `content_block_delta.text_delta` |
| 工具调用 | `delta.tool_calls[]`（id/name 首帧，arguments 分段） | `response.output_item.added`（function_call）+ `response.function_call_arguments.delta` | `content_block_start`（tool_use）+ `content_block_delta.input_json_delta` |
| usage | 收尾 chunk / usage-only chunk | `response.completed.response.usage` | `message_start`（输入）+ `message_delta`（输出） |
| 正常结束 | `finish_reason` ∈ stop/tool_calls/function_call | `status=completed` | `end_turn` / `tool_use` / `stop_sequence` |
| 拒答（完整响应） | 无对应 | 无对应 | `refusal` |
| 截断 | `length`/`max_tokens` | `status=incomplete` + `max_output_tokens` | `max_tokens` |
| 其他终止 | 未知/缺失 finish_reason | 其他 incomplete 原因 | `pause_turn` |

沿用现有分类纪律：只有明确的完整结束归 `stop`；截断、过滤、未知终止归 `length`，避免执行残缺工具参数。Anthropic 的 `refusal` 是带拒答内容的完整响应，归 `stop`；`pause_turn` 表示响应未完成，归 `length`。

anthropic 的 `input_json_delta` 只携带 JSON 片段；适配器按 content block index 聚合，`content_block_start` 提供 id/name，`input_json_delta` 逐段透传为 `ToolCallDelta.arguments_delta`（与现有 tool pipeline 的聚合语义一致）。Responses 的 `output_index` 作为 `ToolCallDelta.index`，`item_id` 作为工具调用 id。

## 元数据消费矩阵

| 字段 | 消费者 | 备注 |
|---|---|---|
| `id` | 适配器 | 线上模型名 |
| `limit.output` | 适配器 | `request.max_tokens` 为空时的默认上限 |
| `tool_call` | 适配器 | `false` 时请求不带 tools |
| `name` / `description` | TUI/文档 | 不参与请求 |
| `limit.context` | 未来 Compactor | 本次仅声明 |
| 其余 | 无 | 文档标注「仅声明」 |

## 失败、可观测与安全

- 启动失败：配置错误、未知 provider/model、密钥缺失 → `error: ...` 写 stderr，无头模式退出码 2、TUI 退出码 2（沿用现有入口）。
- 运行期：适配器把 SDK 异常转 `ProviderError`；`ProviderClient` 保留「首个事件后不重试」的现有语义，避免重放增量。
- 诊断文本沿用 `redact_secrets` 在展示层脱敏；密钥只存在内存中的 `ModelTarget`，不写日志、不进事件。
- 每个 provider 的 `env` 独立解析，不读取全局 `OPENAI_BASE_URL`。

## 测试策略

- 配置层：schema 校验、旧 `model:` 报错、`default_model` 解析、缺密钥、类型与 `api` 组合。
- registry：ref 切分（模型 id 含 `/`）、未知 provider/model、懒解析。
- 适配器：每个协议一组录制事件 fixture，覆盖文本、工具调用分段、usage、正常结束、截断、错误、abort；请求投影断言（system 提升、tool_result 形状、max_tokens）。
- 契约：retry（首事件前可重试、首事件后不重试）、usage 账本、恰好一个 `Done`、流关闭。
- 集成：本地 OpenAI 兼容 mock 端点（`/v1/chat/completions` 流式）跑一次 headless；Responses / Anthropic 的真实网络测试保持显式 opt-in（`integration` marker + 对应密钥）。
- 回归：原先依赖 litellm chunk 类型的录制流已随 litellm 删除；协议行为由 fake SDK 契约测试覆盖。

## 实施顺序

1. ADR 0011 + CONTEXT 术语 + `src/config/providers.py` + 配置测试。验证：`pytest tests/unit/test_yaml_config.py` 与新增配置测试。
2. `provider_registry` + 解析测试。验证：未知 provider/model 报可诊断错误。
3. `openai-compatible` 适配器 + 录制事件测试；`ProviderClient` 接管重试/abort/usage。验证：现有 `tests/llm` 契约在 fake 路径通过。
4. `anthropic` 适配器 + 测试。验证：system/tool_result 投影与 usage 断言。
5. `openai`（Responses）适配器 + 测试。验证：function_call 分段与 incomplete 分类。
6. 装配改造：headless/TUI/runtime 使用 registry；`default_model` 接入；TUI 状态栏显示 ref。验证：本地 mock 端点 headless 冒烟。
7. 删除 litellm、`_skip_mcp_handler` 与旧录制基建；更新 README、`intelliagent.yaml.example`。验证：全量 `pytest`、`ruff`、本地端点冒烟。

## 风险

- 三套消息投影是主要复杂度，尤其 Anthropic `tool_result` 与 Responses item 语义；测试必须覆盖真实历史形状，而不只是单轮。
- 上游协议字段随 SDK 版本变化；锁定 SDK 版本并在升级时跑录制契约。
- 元数据「仅声明」与「配置不静默失效」冲突，已由 ADR 0011 明确接受；后续实现 reasoning/成本账时需同步移除标注。
- 失去 litellm 的 provider 目录，Bedrock/Vertex 用户只能走兼容端点；文档需写明。
- `default_model` 的密钥缺失在启动即失败；多 provider 用户需要为每个 provider 配好环境变量后再使用。

## 未来工作

- Compactor 接线后消费 `limit.context`，并在 TUI 展示上下文占用。
- reasoning 流事件（`ReasoningDelta`）与 TUI 渲染，使 `reasoning` / `interleaved` 生效。
- 成本账：消费 `cost` 与 usage，输出每次 Run 的费用。
- provider 级 `headers` / `body` 覆盖（企业网关、OpenRouter 等）。
- 模型选择器与 `--model` 覆盖。

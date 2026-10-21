# ADR 0011: Provider 配置与原生协议适配器（废除 litellm）

## 状态

已决策，已实施（T0-T4）。取代 ADR 0007 中「LLM 例外：litellm 统一接入多 provider」与 ADR 0010 中「模型接入（litellm）」的决策。设计细节见 `docs/dev/provider-config-design.md`。

## 背景

旧配置把 provider、端点与模型压进一个 `model` 字符串（如 `openai/qwen-max`），端点和密钥只能通过 `OPENAI_BASE_URL` / `OPENAI_API_KEY` 进程级环境变量指定：多 provider 无法共存，密钥无法按来源区分，配置可读性差。同时，本项目只把 litellm 当作一个 `completion()` 调用使用，却承担了 36MB 依赖、隐式环境变量读取，以及 `tools` 非空时无条件导入其 proxy MCP 模块的缺陷（本项目为此需要 `_skip_mcp_handler` 绕过 `mcp>=2.2` 要求）。

## 决策

- 配置改为 provider 中心：`default_model: provider/model-id` + `providers.<id>`（`type`、`api`、`env`、`models`）。
- `type` 决定线协议，支持三种：`openai`（Responses API，`/v1/responses`）、`openai-compatible`（Chat Completions，`/v1/chat/completions`）、`anthropic`（Messages API）。
- 用官方 SDK 实现三个适配器：`openai` SDK 覆盖两种 OpenAI 协议，`anthropic` SDK 覆盖 Messages。SDK 自带重试关闭，重试/超时/abort 仍由 `src/llm/client.py` 统一负责。
- 模型元数据全量进配置（含 `reasoning`、`cost`、`modalities` 等）；暂未消费的字段在文档中标注「仅声明」。
- 删除 litellm 依赖与 `src/llm/litellm_client.py`；旧 `model:` 字段 hard replace，不保留兼容层。

## 被否决的方案

- **保留 litellm，仅在配置层传 `api_base` / `api_key`**：配置体验可以改善，但隐式环境变量、版本漂移与 MCP 导入补丁仍在，且与「可解释架构」的定位不符。
- **纯 httpx 自实现三套 SSE**：零新增依赖、完全可控，但要长期维护三套事件解析与错误映射，收益不抵成本。
- **只支持 openai-compatible**：覆盖面够，但无法正确服务 Anthropic 原生模型与 OpenAI Responses 独有能力。

## 后果

- 配置为破坏性变更：启动时校验 `default_model` 的 provider/model 引用与密钥。
- 失去 litellm 的 provider 目录：Bedrock、Vertex 等原生协议不再支持，只能走其 OpenAI 兼容端点。
- 三个适配器成为长期维护面：上游协议字段变化需跟进，测试需覆盖三套录制事件。
- `reasoning` / `cost` / `modalities` 等元数据暂不产生行为，文档必须明确标注。
- 引擎与 core 不感知 provider：`StreamRequest.model` 仍是 `provider/model-id` 字符串，解析发生在 llm 层。
- 删除 `_skip_mcp_handler` 补丁后，`mcp` 版本不再被 litellm 的 proxy 模块绑架。

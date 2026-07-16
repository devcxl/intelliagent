# ADR：ProviderCatalog 与纯 Config 边界

## 状态

已提议

## 背景

当前 `UnifiedConfig.get_model_context_limit()` 会调用 `src/config/provider_registry.py`。缓存缺失时，该模块同步访问 models.dev
并写 `~/.intelliagent/providers.json`。因此读取配置 getter 会产生网络和文件副作用，并在 async Runtime 路径阻塞事件循环。

项目仍只实现 OpenAI-compatible provider，但 Core 需要稳定 context limit 才能按 ADR 0001 执行压缩。

## 决策

### Config 只负责 typed settings

Config 包允许：

- 读取显式配置文件。
- 环境变量插值。
- Pydantic 校验。
- 无副作用的属性查询。

Config 包禁止网络请求、用户目录缓存读写和 import LLM adapter。

### ProviderCatalog 归 LLM adapter

新增 `src/llm/provider_catalog.py`。Runtime 在 initialize 阶段先读取并校验显式 context limit；只有显式值缺失时才创建
bootstrap-scoped HTTPX client 并调用 ProviderCatalog 查询缓存/远程。正整数结果注入 EngineFactory。EngineFactory、ReactEngine
和 UnifiedConfig 不访问网络或缓存，ProviderCatalog 不 import Config。

### 固定解析优先级

```text
显式 provider/model context limit
  -> 24 小时内有效缓存
  -> 最多 3 秒的 models.dev 远程获取
  -> 启动失败
```

显式配置、缓存和远程三种来源的 context limit 都必须是非 bool 的正整数。缓存 key 是 `provider_id/model_id`，缓存文件 mtime 必须满足
`0 <= age <= 86400`。

远程获取使用 `httpx.AsyncClient`，外层 `asyncio.timeout(3.0)` 覆盖 DNS、连接和响应读取，不重试。成功后使用同目录临时文件
和 `os.replace()` 原子写入缓存。

若远程已经返回可信 context limit，但缓存写入失败，只记录 warning 并继续启动；若配置、缓存和远程都不可用，则 Runtime
启动失败并输出可操作诊断。

### 异步 client 生命周期

- 将 `httpx` 声明为直接依赖。
- P0 先把 OpenAI adapter 改用 `AsyncOpenAI` 并移除 `asyncio.to_thread()`，作为 P1 取消强保证的前置；P2 只迁移
  provider-neutral DTO/port。
- ProviderCatalog 借用 HTTPX client，不负责关闭；Runtime bootstrap 在 context limit 解析后立即退出 client async context。
- LLMClientPort 的 `aclose()` 由 OpenAI adapter 实现为 `await AsyncOpenAI.close()`，Runtime shutdown 显式调用。
- turn cancel 只取消当前 request/stream，不关闭共享 client。

Runtime 将 `provider_id/model_id` 拆分为 provider 引用和 provider model ID。OpenAI adapter 最终发送配置中的 ModelOverride.id
或 model ID，不把完整引用直接传给 SDK。无前缀 model 仅在恰有一个 enabled provider 时有效；零 provider、disabled/unknown
provider 和多 provider 歧义均在启动时失败。现有 model/small_model/provider/enabled_providers/disabled_providers 与 MCP 外部 JSON
结构保持兼容。

配置中的 model key 用于查找显式 `ModelOverride.limit`；非空 `ModelOverride.id`（否则 model key）是 effective model ID，统一用于
ProviderCatalog cache key、models.dev 查询和 SDK model 参数。空字符串 override.id 是配置错误，不回退。

默认缓存路径保持 `~/.intelliagent/providers.json`；新 versioned schema 无法解析旧 raw cache 时按 miss 处理。

## 备选方案

### Config 继续管理缓存和网络

文件更少，但 typed settings getter 继续有隐藏 I/O，测试需要 monkeypatch HOME 和网络，Runtime 也无法明确管理 client 生命周期，
因此不采用。

### 标准库 urllib + asyncio.to_thread

无需直接依赖 httpx，但线程中的 DNS/请求无法提供可靠的 asyncio 取消和 3 秒总 deadline，重现当前 LLM client 的生命周期问题，
因此不采用。

### 缓存永不过期

离线最稳定，但 context limit 变更或 provider 元数据修正永远不会更新。维护者选择 24 小时有效期，因此不采用。

### 远程失败时使用静默默认值

启动更宽松，但会让 ContextManager 在错误窗口大小上运行，违背“配置/缓存均无时启动失败”的需求，因此不采用。

## 后果

正面：

- Config 恢复纯 typed settings 边界。
- async Runtime 不再被同步网络阻塞。
- context limit 来源、缓存有效性和失败行为可确定性测试。
- client 生命周期和取消行为由 Runtime 显式管理。

负面：

- `httpx` 成为直接依赖。
- 首次运行且网络不可用时会明确启动失败。
- 需要维护 versioned cache schema 和原子写入逻辑。

## 与现有 ADR 的关系

- 部分取代 ADR 0002 中 `provider_registry.py` 位于 Config 的模块布局。
- 保留 ADR 0002 的单一 `intelliagent.json`、环境变量插值、Pydantic 校验和配置优先级。
- 支持 ADR 0001 对确定 context limit 的要求，不在 Core 增加 provider-specific cache 逻辑。

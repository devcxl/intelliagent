## Agent Brief

**类别：** architecture / refactor
**摘要：** 收窄 `AgentRuntime` 的组合根职责，避免它继续演变成 service locator 和业务门面。

**关联 Issue：** [#34](https://github.com/devcxl/intelliagent/issues/34)

---

**当前行为：**

`AgentRuntime` 当前同时承担运行时组装和多种具体逻辑：

| 职责 | 当前位置 | 问题 |
|---|---|---|
| 配置加载 | `src/runtime/agent_runtime.py:41` | runtime 自己决定默认配置来源 |
| LLM provider 解析 | `src/runtime/agent_runtime.py:78-111` | provider/model/API key/baseURL 解析不在 llm adapter/factory 层 |
| permission 默认工厂 | `src/runtime/agent_runtime.py:113-134` | 还可以接受，但和其他职责混在一起 |
| skill 扫描 | `src/runtime/agent_runtime.py:140-160` | runtime 直接访问文件系统路径和 SkillLoader |
| DB lifecycle | `src/runtime/agent_runtime.py:49-50`, `181-183`, `272-275` | 组合根职责合理，但和业务代理混杂 |
| tool registry 组装 | `src/runtime/agent_runtime.py:55-62` | 组合逻辑逐渐变复杂 |
| MCP lifecycle | `src/runtime/agent_runtime.py:52`, `266-270` | 组合根职责合理，但缺少独立可测边界 |
| conversation 代理 | `src/runtime/agent_runtime.py:185-214` | runtime 变成 conversation service facade |
| session 执行 | `src/runtime/agent_runtime.py:216-254` | runtime 同时维护 session state |
| engine 创建 | `src/runtime/agent_runtime.py:277-297` | `api_key` / `model` 参数无实际覆盖效果 |

---

**核心问题：**

`AgentRuntime` 名义上是 composition root，实际上已经承担 provider resolver、skill runtime、conversation facade、MCP lifecycle manager、engine factory facade 等多重角色。继续扩展会让所有新能力都自然塞进这个类。

---

**期望行为：**

`AgentRuntime` 应只负责协调生命周期和暴露少量运行时入口。

建议目标边界：

1. `LLMClientFactory` / `ProviderResolver`：负责从 `UnifiedConfig` 解析 model/provider/api key/base url，并创建 `LLMClient`。
2. `SkillRuntime` / `SkillRegistryFactory`：负责 skill 路径解析、扫描、注册。
3. `EngineFactory`：继续负责创建 `ReactEngine`，但接收已经准备好的依赖。
4. `ConversationSession`：继续负责跨轮复用 engine 和消息持久化。
5. `AgentRuntime`：只负责初始化/关闭这些组件，并提供 `execute()` 主入口。

---

**建议实现步骤：**

1. **提取 LLMClientFactory**
   - 文件建议：`src/llm/factory.py` 或 `src/runtime/llm_factory.py`。
   - 输入：`UnifiedConfig`。
   - 输出：`LLMClientProtocol`。
   - 迁移 `AgentRuntime._default_llm_client_factory()` 中的 provider/model 解析逻辑。

2. **提取 SkillRegistryFactory**
   - 文件建议：`src/skills/runtime.py` 或 `src/runtime/skill_runtime.py`。
   - 输入：`SkillsConfig` 和 workspace path。
   - 输出：`SkillRegistry | None`。
   - 迁移 `AgentRuntime._load_skills()`。

3. **清理 create_engine API**
   - 当前 `create_engine(api_key=None, model=None, ...)` 的 `api_key` 和 `model` 不影响实际创建。
   - 维护者已决定删除无效参数，不实现临时 override。
   - 清理后 `create_engine()` 只保留真实生效的参数。

4. **减少 conversation facade 面积**
   - 本 issue 不删除 `save_message()`。
   - 如后续确认该方法可移除，应单独开 issue 处理。
   - 保留 CLI 需要的 `setup_conversation()`、`list_conversations()`、`get_message_count()`，但不要继续向 runtime 添加更多业务代理。

5. **补测试**
   - LLM factory：覆盖 provider_id/model_id 命中、无 provider_id 回退、缺 API key 报错。
   - Skill registry factory：覆盖 disabled、project path、user path、同名优先级。
   - Runtime：只验证组装和 lifecycle，不重复测试 factory 内部细节。

---

**验收标准：**

- [ ] `AgentRuntime` 不直接解析 `provider` 字段中的 API key/baseURL。
- [ ] `AgentRuntime` 不直接调用 `SkillLoader.load()`。
- [ ] `create_engine()` 不再暴露无效的 `api_key` / `model` 参数。
- [ ] 新增 LLM factory 单元测试。
- [ ] 新增 skill registry factory 单元测试。
- [ ] 现有 CLI 和 runtime tests 通过。
- [ ] `uv run pytest --tb=short` 通过。
- [ ] `ruff check .` 和 `ruff format --check .` 通过。

---

**不在范围内：**

- 不重写 `ReactEngine`；该工作属于 #30。
- 不重写上下文压缩；该工作属于 #31。
- 不改变 permission rule 语义。
- 不改变 DB schema。
- 不引入 service container 或复杂 DI 框架。

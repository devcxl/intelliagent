# 开发方案: Issue #34 — 收窄 AgentRuntime 的组合根职责

**Project:** architecture-cleanup
**Issue:** #34
**类型:** refactor
**风险等级:** 高
**建议执行方式:** 分离 provider factory 和 skill factory，避免大规模重写 runtime

---

## 1. 目标

让 `AgentRuntime` 回到组合根角色，只负责生命周期协调和少量运行时入口。provider 解析、skill 扫描等具体逻辑移入专门工厂。

---

## 2. 当前切入点

重点文件：

| 文件 | 当前问题 |
|---|---|
| `src/runtime/agent_runtime.py` | 同时做 provider 解析、skill 扫描、DB/MCP/session lifecycle、conversation facade |
| `src/runtime/engine_factory.py` | 已经是较清晰的 engine 组装 seam，可以保留 |
| `src/llm/llm_client.py` | 只接收显式参数，缺少从 config 创建 client 的 factory |
| `src/skills/loader.py` / `registry.py` | skill 加载能力存在，但 runtime 直接编排路径解析 |

建议新增文件：

| 文件 | 责任 |
|---|---|
| `src/llm/factory.py` | 从 `UnifiedConfig` 创建 `LLMClientProtocol` |
| `src/skills/runtime.py` | 从 `SkillsConfig` + workspace 创建 `SkillRegistry | None` |
| `tests/unit/test_llm_factory.py` | 覆盖 provider/model 解析 |
| `tests/unit/test_skill_runtime.py` | 覆盖 skill loading orchestration |

---

## 3. 分阶段实现

### 阶段 0：建立 runtime 基线

执行：

```bash
uv run pytest tests/unit/test_skill_runtime_integration.py tests/unit/test_skill_engine_integration.py --tb=short
```

再执行 runtime/engine 相关测试：

```bash
uv run pytest tests/unit/test_react_engine.py tests/integration/test_react_engine_e2e.py --tb=short
```

---

### 阶段 1：提取 LLMClientFactory

新增 `src/llm/factory.py`。

建议接口：

```python
class LLMClientFactory:
    def __init__(self, config: UnifiedConfig) -> None: ...
    def create(self) -> LLMClientProtocol: ...
```

迁移 `AgentRuntime._default_llm_client_factory()` 逻辑：

- `model` 格式为 `provider_id/model_id` 时优先取对应 provider。
- 无 provider_id 时遍历 provider config 找第一个可用 `apiKey/baseURL`。
- 创建 `LLMClient(api_key=..., base_url=..., model=...)`。

测试覆盖：

| 用例 | 断言 |
|---|---|
| model 带 provider id | 使用对应 provider options |
| model 不带 provider id | fallback 到第一个 provider options |
| provider options 缺 baseURL | base_url 为 `None` |
| 未配置 api key | 保持当前行为，不在本 issue 新增报错 |

修改 `AgentRuntime.__init__()`：

```python
self._llm_client_factory = llm_client_factory or LLMClientFactory(self._config).create
```

验证：

```bash
uv run pytest tests/unit/test_llm_factory.py --tb=short
```

---

### 阶段 2：提取 SkillRuntime

新增 `src/skills/runtime.py`。

建议接口：

```python
class SkillRuntime:
    def __init__(self, config: SkillsConfig, workspace: Path) -> None: ...
    def load_registry(self) -> SkillRegistry | None: ...
```

迁移 `AgentRuntime._load_skills()` 逻辑：

- disabled 时返回 `None`。
- project paths 按 workspace 解析。
- user paths 按 `expanduser().resolve()` 解析。
- 使用 `SkillLoader.load()` 和 `SkillRegistry.load_all()`。
- 无 skills 时返回 `None`。

测试覆盖：

| 用例 | 断言 |
|---|---|
| skills disabled | 返回 `None` |
| 无 skill 文件 | 返回 `None` |
| project skill 可加载 | registry 包含 skill |
| project/user 同名 | project 优先 |

修改 `AgentRuntime.__init__()`：

```python
self._skill_registry = SkillRuntime(self._config.skills, Path(self._config.workspace.dir)).load_registry()
```

删除或简化 `_load_skills()`。

验证：

```bash
uv run pytest tests/unit/test_skill_runtime.py tests/unit/test_skill_runtime_integration.py --tb=short
```

---

### 阶段 3：清理 create_engine API

当前 `AgentRuntime.create_engine(api_key=None, model=None, ...)` 的 `api_key` 和 `model` 参数无实际覆盖效果。

维护者已决定删除无效参数，不实现临时 override。修改后只保留：

```python
async def create_engine(
    self,
    compact_callback: Callable[[list[str], str], Awaitable[None]] | None = None,
) -> ReactEngine:
```

如果存在测试或调用方传入 `api_key/model`，需要同步更新。

验证：

```bash
uv run pytest tests/unit tests/integration --tb=short
```

---

### 阶段 4：收敛 AgentRuntime public surface

不要大规模删除 public 方法。先做低风险整理：

- 保留 CLI 需要的 `initialize()`、`setup_conversation()`、`execute()`、`list_conversations()`、`get_message_count()`、`shutdown()`。
- 本 issue 不删除 `save_message()`；如后续确认可移除，再单独开 issue。
- 给 `AgentRuntime` 类 docstring 更新职责描述：生命周期协调，而非 provider/skill 解析。

---

## 4. 测试计划

新增/更新测试：

| 测试文件 | 覆盖 |
|---|---|
| `tests/unit/test_llm_factory.py` | provider/model/API 参数解析 |
| `tests/unit/test_skill_runtime.py` | skill disabled、路径解析、同名优先级 |
| runtime 现有测试 | runtime 组装行为不变 |

最终验证：

```bash
uv run pytest --tb=short
ruff check .
ruff format --check .
```

---

## 5. 风险与控制

| 风险 | 控制 |
|---|---|
| provider 创建行为变化 | LLMClientFactory 测试覆盖旧行为 |
| skill 加载路径变化 | SkillRuntime 测试使用 tmp_path 覆盖 project/user paths |
| runtime 构造参数变复杂 | 保持现有 `llm_client_factory` 注入 seam |
| 删除 create_engine 参数破坏外部调用 | 先 grep 调用点，只更新本仓库内调用；若外部 API 需要兼容，则保留参数但标记 deprecated 并让其生效 |

---

## 6. 完成定义

- `AgentRuntime` 不再直接解析 provider options。
- `AgentRuntime` 不再直接调用 `SkillLoader.load()`。
- `create_engine()` 不暴露无效参数。
- 新增 factory/runtime 单元测试。
- 全量测试和 lint 通过。

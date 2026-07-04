# 开发方案: Issue #30 — 拆分 ReactEngine 的多重职责

**Project:** architecture-cleanup
**Issue:** #30
**类型:** refactor
**风险等级:** 高
**建议执行方式:** 分 3 个小 PR 或 3 个独立 commit 完成

---

## 1. 目标

将 `ReactEngine` 收窄为 ReAct loop 编排器。工具执行、权限检查和事件构造从 `ReactEngine` 中移出，保持外部行为不变。

本 issue 不处理上下文压缩策略重做；上下文压缩属于 #31。

---

## 2. 当前切入点

重点文件：

| 文件 | 当前问题 |
|---|---|
| `src/core/react_engine.py` | 同时处理 loop、messages、permission、tool execution、events、OpenAI tool-call shape |
| `tests/unit/test_react_engine.py` | 现有测试混合覆盖 loop 和工具执行细节 |
| `tests/integration/test_react_engine_e2e.py` | 需要作为行为回归保护 |

建议新增文件：

| 文件 | 责任 |
|---|---|
| `src/core/tool_executor.py` | 解析 tool call、权限检查、调用 registry、返回执行结果 |
| `src/core/events.py` | 构造 `thought/action/observation/answer` 事件 |
| `tests/unit/test_tool_executor.py` | 覆盖工具执行与权限分支 |

---

## 3. 分阶段实现

### 阶段 0：建立回归基线

执行命令：

```bash
uv run pytest tests/unit/test_react_engine.py tests/integration/test_react_engine_e2e.py --tb=short
```

通过后再进入代码修改。若失败，先记录失败，不要把无关失败混进本 issue。

---

### 阶段 1：提取 ToolExecutor

新增 `src/core/tool_executor.py`。

建议最小接口：

```python
@dataclass
class ToolExecutionResult:
    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]
    content: str
    status: str = "success"
    error: str | None = None


class ToolExecutor:
    async def execute(self, tool_call: dict[str, Any]) -> ToolExecutionResult: ...
```

迁移逻辑：

| 旧位置 | 新位置 |
|---|---|
| `ReactEngine.execute_tool()` | `ToolExecutor.execute()` |
| `ReactEngine._parse_tool_args()` | `ToolExecutor._parse_tool_args()` |
| permission decision 分支 | `ToolExecutor._check_permission()` 或内联私有逻辑 |
| registry call | `ToolExecutor.execute()` |

保持返回给 LLM 的 `content` 字符串不变，不改变工具响应 JSON 格式。

验证：

```bash
uv run pytest tests/unit/test_tool_executor.py tests/unit/test_react_engine.py --tb=short
```

---

### 阶段 2：提取事件构造

新增 `src/core/events.py`。

建议接口：

```python
def answer_event(step: int, content: str | None, total_tokens: int, usage: TokenUsageView) -> dict[str, Any]: ...
def thought_event(step: int, content: str | None, tool_calls: list[dict[str, Any]] | None) -> dict[str, Any]: ...
def action_event(step: int, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]: ...
def observation_event(step: int, result: ToolExecutionResult) -> dict[str, Any]: ...
```

保持现有事件 shape 完全兼容：

- `type`
- `iteration`
- `data`
- observation 中的 `tool_call_id`、`tool_name`、`tool_args`、`result`、`status`、`error`、`execution_time`

验证：

```bash
uv run pytest tests/unit/test_react_engine.py tests/integration/test_react_engine_e2e.py --tb=short
```

---

### 阶段 3：收窄 ReactEngine

修改 `ReactEngine.__init__()`：

- 保留现有构造参数，避免破坏 runtime。
- 在构造函数内部创建 `ToolExecutor`。
- 或允许注入 `tool_executor`，默认从已有依赖构造。

修改 `_execute_tool_calls()`：

```python
for tool_call in tool_calls:
    result = await self._tool_executor.execute(tool_call)
    yield action_event(step, result.tool_name, result.tool_args)
    self.add_tool_message(result.tool_call_id, result.content)
    yield observation_event(step, result)
```

注意：如果要保持 action 在工具执行前 yield，可以先解析 args 再执行。行为应和当前一致：先 yield action，再 execute，再 add tool message，再 yield observation。

最终 `ReactEngine` 不应再直接知道 permission callback 和 registry 调用细节。

验证：

```bash
uv run pytest --tb=short
ruff check .
ruff format --check .
```

---

## 4. 测试计划

新增 `tests/unit/test_tool_executor.py`，覆盖：

| 用例 | 断言 |
|---|---|
| allow 执行成功 | registry 被调用，返回 success content |
| deny | registry 不被调用，返回权限拒绝 content |
| ask + approved | callback 被调用，registry 被调用 |
| ask + rejected | registry 不被调用，返回用户拒绝 |
| ask + 无 callback | registry 不被调用，返回需要确认但无回调 |
| invalid JSON args | args fallback 为 `{}` |
| unknown tool | 透传 registry 的 unknown tool 响应 |

回归测试：

```bash
uv run pytest tests/unit/test_tool_executor.py tests/unit/test_react_engine.py tests/integration/test_react_engine_e2e.py --tb=short
```

最终全量：

```bash
uv run pytest --tb=short
ruff check .
ruff format --check .
```

---

## 5. 风险与控制

| 风险 | 控制 |
|---|---|
| 事件格式变化导致 CLI 或测试失败 | 事件构造函数必须复刻旧 shape，并用现有测试保护 |
| 工具执行顺序变化 | 保持 action 在 execute 前，observation 在 execute 后 |
| permission 行为变化 | ToolExecutor 单测覆盖所有 decision 分支 |
| 改动过大 | 不碰上下文压缩和 provider abstraction |

---

## 6. 完成定义

- `ReactEngine` 不直接调用 permission engine、permission callback、tool registry。
- 新增 `ToolExecutor` 并有单元测试。
- 事件构造集中，外部事件 shape 不变。
- 全量测试和 lint 通过。

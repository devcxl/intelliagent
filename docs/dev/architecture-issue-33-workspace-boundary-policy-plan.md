# 开发方案: Issue #33 — 统一权限和文件工具的 workspace 边界策略

**Project:** architecture-cleanup
**Issue:** #33
**类型:** security / refactor
**风险等级:** 高
**建议执行方式:** 先集中路径策略，再接入 permission 和 file tools

---

## 1. 目标

让 permission engine 和 file tools 使用同一套 workspace/external directory 判断，消除 `UnifiedConfig.workspace.dir`、`workspace_root` 参数和 `INTELLIAGENT_WORKSPACE_ROOT` 之间的语义漂移。

---

## 2. 当前切入点

重点文件：

| 文件 | 当前问题 |
|---|---|
| `src/permission/engine.py` | 内部直接调用 `is_path_in_workspace()` 和 `is_in_external_directories()` |
| `src/tools/file_tools.py` | 自己解析 workspace root，不了解 external directories |
| `src/utils/path_utils.py` | 仅提供散装函数，且 `resolve_workspace_root()` 依赖 env |
| `src/tools/registry.py` | 默认注册文件工具时未绑定 runtime workspace |
| `src/runtime/agent_runtime.py` | permission 用 config workspace，file tools 未使用同一配置 |

建议新增文件：

| 文件 | 责任 |
|---|---|
| `src/utils/path_policy.py` | 单一路径边界策略 |
| `tests/unit/test_path_policy.py` | 覆盖 workspace/external/relative path 语义 |

---

## 3. 设计方案

新增 `PathPolicy`，作为唯一判断路径边界的对象。

维护者已确认采用“双层防线”：PermissionEngine 和 file tools 都使用同一个 `PathPolicy`。PermissionEngine 负责权限动作决策，file tools 负责最终结构性拦截。

建议接口：

```python
@dataclass(frozen=True)
class PathCheckResult:
    allowed_by_boundary: bool
    in_workspace: bool
    in_external_directory: bool
    resolved_path: Path | None
    reason: str = ""


@dataclass(frozen=True)
class PathPolicy:
    workspace: Path
    external_directories: tuple[Path, ...] = ()

    def check(self, path: str | Path) -> PathCheckResult: ...
```

语义：

| 场景 | 结果 |
|---|---|
| 空 path | `allowed_by_boundary=True`，兼容无路径工具 |
| 相对路径 | 先按 `workspace / path` 解析 |
| workspace 内 | `allowed_by_boundary=True`, `in_workspace=True` |
| workspace 外且在 external directory | `allowed_by_boundary=True`, `in_external_directory=True` |
| workspace 外且不在 external directory | `allowed_by_boundary=False` |
| 路径无法解析 | `allowed_by_boundary=False`，reason 包含错误 |

---

## 4. 分阶段实现

### 阶段 0：建立安全测试基线

先运行现有权限和文件工具测试：

```bash
uv run pytest tests/unit/test_permission_engine.py tests/unit/test_permission_integration.py --tb=short
```

如果没有专门 file tools 测试，记录缺口，并在本 issue 中补齐关键路径测试。

---

### 阶段 1：新增 PathPolicy

新增 `src/utils/path_policy.py`。

实现要求：

- 不依赖环境变量。
- 构造时 workspace 必须显式传入。
- external directories 在构造时 resolve 成 tuple。
- 相对路径统一按 workspace root 解析。

新增 `tests/unit/test_path_policy.py`，覆盖：

- workspace 内相对路径。
- workspace 内绝对路径。
- workspace 外路径。
- external directory 内路径。
- 空 path。
- 路径解析异常可用 monkeypatch 或不可访问路径模拟。

验证：

```bash
uv run pytest tests/unit/test_path_policy.py --tb=short
```

---

### 阶段 2：接入 PermissionEngine

修改 `PermissionEngine.__init__()`：

- 可以接收 `path_policy: PathPolicy | None`。
- 为减少调用方破坏，也可以保留 `workspace` 和 `external_directories` 参数，在内部创建 `PathPolicy`。

修改 `check()`：

- 使用 `self._path_policy.check(path)`。
- workspace 外且不在 external directory 返回 deny。
- external directory 内返回 ask。
- 默认规则语义不变。

验证：

```bash
uv run pytest tests/unit/test_permission_engine.py tests/unit/test_permission_integration.py --tb=short
```

---

### 阶段 3：接入 file_tools

最小改法：给文件工具增加可注入 policy 参数，同时保留 `workspace_root` 兼容直接调用。

建议签名：

```python
async def read_file(path: str, workspace_root: str | None = None, path_policy: PathPolicy | None = None) -> str: ...
```

边界检查函数：

```python
def _check_workspace_boundary(file_path: pathlib.Path, path_policy: PathPolicy | None, workspace_root: str | None) -> str | None: ...
```

优先级：

1. 如果传入 `path_policy`，只用 policy。
2. 否则保留旧 `workspace_root` / env 行为，避免直接调用破坏。
3. Runtime 注册的默认工具必须使用 policy。

验证：新增 file tools 测试覆盖 policy 分支。

---

### 阶段 4：调整 ToolRegistryFactory 和 Runtime

修改 `ToolRegistryFactory`：

- 新增 `path_policy: PathPolicy | None` 参数。
- 注册 `read_file/write_file/edit_file` 时使用闭包绑定 policy。

示例：

```python
async def read_file_with_policy(path: str) -> str:
    return await read_file(path=path, path_policy=self._path_policy)
```

修改 `AgentRuntime._create_tool_registry()`：

- 基于 `self._config.workspace.dir` 和 `self._config.permissions.external_directories` 构造 `PathPolicy`。
- 传给 `ToolRegistryFactory`。

验证：

```bash
uv run pytest tests/unit/test_tool_registry.py tests/unit/test_permission_engine.py --tb=short
```

---

## 5. 测试计划

新增/更新测试覆盖：

| 用例 | 断言 |
|---|---|
| PathPolicy workspace 内相对路径 | allowed |
| PathPolicy workspace 外路径 | denied |
| PathPolicy external directory | allowed_by_boundary 且 `in_external_directory=True` |
| PermissionEngine workspace 外 | deny |
| PermissionEngine external directory | ask |
| file_tools policy 拒绝 workspace 外路径 | 返回 `PATH_OUTSIDE_WORKSPACE` 或等价错误 |
| ToolRegistryFactory 注册的文件工具使用 runtime policy | 不依赖 `INTELLIAGENT_WORKSPACE_ROOT` |

最终验证：

```bash
uv run pytest --tb=short
ruff check .
ruff format --check .
```

---

## 6. 风险与控制

| 风险 | 控制 |
|---|---|
| 安全行为变化 | 用 PathPolicy 单测固定所有路径分类 |
| 直接调用 file_tools 的测试被破坏 | 保留 `workspace_root` 兼容路径 |
| external directory 被文件工具误拒绝 | file tools 使用同一个 PathPolicy |
| registry 闭包导致函数名/schema 混乱 | 注册 name/schema 保持原样，只替换 function wrapper |

---

## 7. 完成定义

- Runtime 默认文件工具不依赖 `INTELLIAGENT_WORKSPACE_ROOT`。
- PermissionEngine 和 file tools 使用同一 workspace/external directory 语义。
- 路径边界有集中单元测试。
- 全量测试和 lint 通过。

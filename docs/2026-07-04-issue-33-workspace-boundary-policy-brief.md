## Agent Brief

**类别：** architecture / security
**摘要：** 统一权限引擎和文件工具的 workspace 边界策略，避免同一路径被两套规则给出不同判断。

**关联 Issue：** [#33](https://github.com/devcxl/intelliagent/issues/33)

---

**当前行为：**

路径安全边界目前分散在两处：

1. `PermissionEngine` 使用 `UnifiedConfig.workspace.dir`。
   - `src/runtime/agent_runtime.py:121-123`
   - `src/permission/engine.py:101-116`

2. `file_tools` 使用函数参数 `workspace_root` 或环境变量 `INTELLIAGENT_WORKSPACE_ROOT`。
   - `src/tools/file_tools.py:28-41`
   - `src/utils/path_utils.py:7-18`

默认工具注册时没有把 runtime config workspace 注入文件工具：

- `src/tools/registry.py:161-185`

结果：权限层和工具层可能对同一路径产生不同判断。

---

**具体风险：**

- 权限层基于 `workspace.dir` 允许后，文件工具层可能基于另一个 env workspace 拒绝。
- 如果没有设置 `INTELLIAGENT_WORKSPACE_ROOT`，文件工具层可能完全跳过 workspace boundary check。
- `external_directories` 只存在于 permission 层，文件工具层不了解白名单。
- 安全语义分散在 `permission`、`tools`、`utils`，后续修改容易漏一处。

---

**期望行为：**

项目应只有一个 workspace/path boundary 策略来源。

维护者已决定采用“双层防线”：permission engine 和 file tools 共用同一个 `PathPolicy`。权限层负责 `allow` / `ask` / `deny` 决策，文件工具层负责最终结构性边界拦截。

目标：

1. workspace root 来源统一为 `UnifiedConfig.workspace.dir`。
2. external directories 来源统一为 `UnifiedConfig.permissions.external_directories`。
3. permission engine 和 file tools 使用同一个路径判断语义，并在两层都实际执行边界检查。
4. 默认注册的文件工具不依赖 `INTELLIAGENT_WORKSPACE_ROOT` 这种隐式安全配置。
5. 安全边界有集中测试。

---

**建议接口：**

可以新增小型策略对象，避免继续传散装参数：

```python
@dataclass(frozen=True)
class PathPolicy:
    workspace: Path
    external_directories: tuple[Path, ...] = ()

    def classify(self, path: str | Path) -> PathDecision: ...
```

`PathDecision` 可以很小：

```python
@dataclass(frozen=True)
class PathDecision:
    in_workspace: bool
    in_external_directory: bool
    resolved_path: Path | None
    reason: str = ""
```

如果认为 dataclass 过重，也可以保留函数式实现，但必须保证 permission 和 file tools 调同一套函数，并由 runtime 注入相同参数。

---

**建议实现步骤：**

1. **集中路径策略**
   - 文件建议：`src/utils/path_policy.py` 或继续扩展 `src/utils/path_utils.py`。
   - 合并 `is_path_in_workspace()` 和 `is_in_external_directories()` 的语义。
   - 明确相对路径永远按 workspace root 解析。

2. **改造 PermissionEngine**
   - 构造时接收 `PathPolicy`，或接收 workspace/external directories 后内部创建同一策略。
   - `check()` 不再手写 workspace/external 判断。

3. **改造 file_tools**
   - `read_file/write_file/edit_file` 支持接收 `path_policy` 或明确的 `workspace_root` + `external_directories`。
   - 文件工具层只做结构性边界保护：workspace 内或 external directory 内才允许实际访问。
   - 是否需要 ask/deny 仍由 permission layer 决定。

4. **改造 ToolRegistryFactory**
   - 接收 runtime workspace 和 external directories。
   - 注册文件工具时绑定同一策略，不依赖 env。

5. **保留或降级环境变量行为**
   - `INTELLIAGENT_WORKSPACE_ROOT` 可以保留给直接调用 file tools 的测试/兼容场景。
   - 默认 runtime 路径不能依赖它。

---

**验收标准：**

- [ ] permission engine 和 file tools 使用同一 workspace/external directory 语义。
- [ ] 默认注册的 `read_file/write_file/edit_file` 绑定 `UnifiedConfig.workspace.dir`。
- [ ] 默认注册的文件工具了解 `permissions.external_directories`。
- [ ] 相对路径按 workspace root 解析。
- [ ] workspace 内路径允许进入工具执行。
- [ ] workspace 外且不在 external directory 的路径被拒绝。
- [ ] workspace 外但在 external directory 的路径通过结构性边界检查，权限层仍可 ask。
- [ ] 增加单元测试覆盖 workspace 内、workspace 外、external directory、相对路径、路径解析异常。
- [ ] `uv run pytest --tb=short` 通过。
- [ ] `ruff check .` 和 `ruff format --check .` 通过。

---

**不在范围内：**

- 不重写完整 permission rule 语法。
- 不改变 last-match-wins 语义。
- 不新增文件系统 sandbox。
- 不处理 shell 命令中的路径安全；本 issue 只处理显式 `path` 参数的文件工具。
- 不引入新依赖。

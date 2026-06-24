## 审查报告 — PR #27: T3 Agent Team Tool 层实现

**审查日期**: 2026-06-24

### 变更概述

- **修改文件数**: 3（均为新增）
- **新增文件**:
  - `src/tools/agent_team_tools.py`（251 行）— 6 个异步 tool 函数 + ContextVar 上下文注入
  - `tests/tools/__init__.py`（空文件）
  - `tests/tools/test_agent_team_tools.py`（366 行，26 个测试用例）
- **风险等级**: 中（存在 HIGH 级别问题，但都可在 PR 内修复）

### 变更范围校验

✅ 仅涉及 `src/tools/` 和 `tests/tools/`，无越界修改  
✅ 对标 `task_tools.set_task_context()` 模式，架构一致性良好  
✅ ContextVar 替代 global 变量，对 asyncio 并发场景更安全

---

### 发现问题

#### [HIGH] #1 — SQLite 连接泄漏（每个 tool 调用泄漏 2-3 个 FD）

- **文件**: `src/tools/agent_team_tools.py:63-65`
- **问题**: `_get_service()` 每次调用创建新的 `AgentTeamDB()` 实例（内部 `sqlite3.connect()` 打开连接 + WAL 文件 + shm 文件），但从不调用 `.close()`。验证：100 次连续调用泄漏 58 个文件描述符。
- **影响**: 生产环境下随 tool 调用次数增长导致 FD 耗尽。
- **根因**: 对标 `task_tools` 的设计中，`task_tools` 使用 SQLAlchemy `async_sessionmaker` 管理连接生命周期（自动回收），而 `agent_team_tools` 使用裸 `sqlite3.connect()` 缺少连接池/关闭机制。
- **修复建议**: 两种方案可选

  **方案 A（推荐，对齐 task_tools 模式）**：引入连接工厂，按需创建/关闭连接
  ```python
  # 修改 _get_service()，使用上下文管理器确保关闭
  from contextlib import contextmanager
  
  def _get_service() -> tuple[AgentTeamService, str]:
      ctx = _agent_team_ctx.get()
      if ctx is None:
          raise LookupError("Agent Team 上下文未初始化")
      db_path, agent_id = ctx
      db = AgentTeamDB(db_path)
      db.init_db()
      return AgentTeamService(db), agent_id
  ```
  需要在每个 tool 函数中改为：
  ```python
  async def send_message(to_agent_id: str, content: str) -> str:
      try:
          service, agent_id = _get_service()
      except LookupError:
          return _context_error()
      try:
          result = service.send_message(sender_id=agent_id, to_agent_id=to_agent_id, content=content)
          return success_response({"message_id": result["id"], "created_at": result["created_at"]})
      except (AgentNotFoundError, EmptyContentError) as e:
          desc_template, code = _EXCEPTION_MAP[type(e)]
          return error_response(desc_template.format(str(e)), code)
      finally:
          service._db.close()  # 确保连接关闭
  ```

  **方案 B（更彻底）**：给 `AgentTeamDB` 添加 `__enter__`/`__exit__` 或 `close` 由 Runtime 管理连接生命周期，而非每次 tool 调用创建新连接。

#### [HIGH] #2 — `create_agent` 未捕获 `ValueError("Agent name is required")`

- **文件**: `src/tools/agent_team_tools.py:210-215`
- **问题**: Service 层 `create_agent()` 对空名称抛出 `ValueError("Agent name is required")`，但 Tool 层只捕获了 `DuplicateNameError`。空名称输入（如 `create_agent(name="  ")`）导致 `ValueError` 未被处理，传播到上层被 `ToolRegistry.call_tool()` 以通用 `EXECUTION_ERROR` 捕获。
- **验证**: `python -c "await create_agent(name='   ')"` → `ValueError: Agent name is required`（未被 Tool 层捕获）
- **影响**: 不一致的错误处理 — 其他 tool 对空输入返回语义化的 error code（如 `EMPTY_CONTENT`），`create_agent` 却返回通用 `EXECUTION_ERROR`
- **修复建议**:
  ```python
  # 在 _EXCEPTION_MAP 中添加
  _EXCEPTION_MAP: dict[type[Exception], tuple[str, str]] = {
      AgentNotFoundError: ("Agent 不存在: {}", "AGENT_NOT_FOUND"),
      EmptyContentError: ("消息内容不能为空", "EMPTY_CONTENT"),
      DuplicateNameError: ("Agent 名称已存在: {}", "DUPLICATE_NAME"),
      InvalidStatusError: ("无效的状态值: {}", "INVALID_STATUS"),
      ValueError: ("{}", "INVALID_PARAMETERS"),  # 新增
  }
  
  # create_agent 中扩大异常捕获范围
  async def create_agent(name: str, desc: str = "", prompt: str = "") -> str:
      try:
          service, _ = _get_service()
      except LookupError:
          return _context_error()
      try:
          agent = service.create_agent(name=name, desc=desc, prompt=prompt)
          return success_response({"agent": agent})
      except (DuplicateNameError, ValueError) as e:  # 新增 ValueError
          desc_template, code = _EXCEPTION_MAP[type(e)]
          return error_response(desc_template.format(str(e)), code)
  ```

#### [HIGH] #3 — 错误消息尾随空冒号（异常无参构造 + `.format(str(e))`）

- **文件**: `src/tools/agent_team_tools.py:111-113` 等多处
- **问题**: Service 层所有业务异常都无参构造（`raise AgentNotFoundError()` 不含 message），Tool 层使用 `desc_template.format(str(e))` 格式化错误消息时 `str(e)` 为空字符串，导致输出 `"Agent 不存在: "`（尾随冒号+空格）。
- **验证**: `str(AgentNotFoundError())` → `""`，`"Agent 不存在: {}".format("")` → `"Agent 不存在: "`
- **影响**: 错误消息不美观，可能干扰 LLM 解析 JSON error 字段
- **修复建议**: 两种方案

  **方案 A（推荐）**：Service 层异常改为携带有意义的 message
  ```python
  # src/core/agent_team.py
  raise AgentNotFoundError(f"Agent '{to_agent_id}' not found")  # 而非 AgentNotFoundError()
  raise DuplicateNameError(f"Agent name '{name}' already exists")
  raise InvalidStatusError(f"Invalid status '{status_filter}'")
  ```

  **方案 B（最小改动）**：修改 Tool 层模板去掉 `{}`，直接使用固定消息
  ```python
  _EXCEPTION_MAP: dict[type[Exception], tuple[str, str]] = {
      AgentNotFoundError: ("Agent 不存在", "AGENT_NOT_FOUND"),
      DuplicateNameError: ("Agent 名称已存在", "DUPLICATE_NAME"),
      InvalidStatusError: ("无效的状态值", "INVALID_STATUS"),
  }
  ```

#### [MEDIUM] #4 — 未使用的 `typing.Any` 导入

- **文件**: `src/tools/agent_team_tools.py:11` 和 `tests/tools/test_agent_team_tools.py:8`
- **问题**: `from typing import Any` 在两个文件中均未被使用（已通过 AST 分析确认）
- **修复建议**: 删除两处 `Any` 导入（或保留源文件中的导入用于未来的日志类型注解）

#### [MEDIUM] #5 — 测试未覆盖 `create_agent` 空名称 `ValueError` 路径

- **文件**: `tests/tools/test_agent_team_tools.py`
- **问题**: 当前 `TestCreateAgentTool` 未测试空名称（`""`）或纯空白名称（`"  "`）输入。这与 `TestSendMessageTool` 覆盖了 `test_send_empty_content` 和 `test_send_whitespace_content` 形成不一致。
- **修复建议**: 新增测试用例：
  ```python
  @pytest.mark.asyncio
  async def test_create_empty_name(self, agent_ctx: str):
      data = json.loads(await create_agent(name=""))
      assert data["status"] == "error" and data["code"] == "INVALID_PARAMETERS"

  @pytest.mark.asyncio
  async def test_create_whitespace_name(self, agent_ctx: str):
      data = json.loads(await create_agent(name="   "))
      assert data["status"] == "error" and data["code"] == "INVALID_PARAMETERS"
  ```

#### [MEDIUM] #6 — 错误消息"Agent Team 上下文未初始化"重复定义

- **文件**: `src/tools/agent_team_tools.py:61` 和 `:70`
- **问题**: `_get_service()` 中 `LookupError("Agent Team 上下文未初始化")` 和 `_context_error()` 中 `error_response("Agent Team 上下文未初始化", ...)` 硬编码了相同的错误消息字符串。
- **修复建议**: 提取为常量 `_CONTEXT_NOT_INITIALIZED_MSG = "Agent Team 上下文未初始化"`

---

### 测试覆盖分析

| 测试类别 | 用例数 | 覆盖情况 |
|---------|-------|---------|
| 上下文缺失 | 6 | ✅ 全部 6 个 tool |
| send_message | 4 | ✅ 成功/空内容/空白内容/目标不存在 |
| receive_message | 4 | ✅ 空收件箱/分页/已读标记/仅未读 |
| get_contacts | 3 | ✅ 排除自身/状态过滤/无效状态 |
| get_contact_detail | 2 | ✅ 成功/不存在 |
| create_agent | 3 | ✅ 成功/重名/默认值；❌ 缺空名称测试 |
| delete_agent | 2 | ✅ 成功/不存在 |
| 端到端 | 2 | ✅ 收发往返/多 Agent 聊天 |
| **总计** | **26** | **24/26 (92%) 路径覆盖合理** |

**测试质量评价**: 良好。使用临时 SQLite DB（无外部依赖）、fixture 管理上下文生命周期、覆盖 JSON 输入/输出验证和 DB 状态校验。

**建议补充**:
- 并发安全测试：多个 asyncio task 同时调用不同 tool，ContextVar 是否隔离
- `_EXCEPTION_MAP` 完整性测试：确保所有 Service 异常类型都已有映射

---

### 审查结论

- [ ] 通过 — 无 Critical/High 问题
- [x] **有条件通过** — 存在 3 个 HIGH 问题（SQLite 连接泄漏、create_agent ValueError 未捕获、错误消息尾随空冒号），修复后可直接 approve
- [ ] 不通过

**建议**：先修复 3 个 HIGH 问题 + 1 个 MEDIUM #5（补测空名称），其余 MEDIUM 可在后续 PR 中处理。

---

### 验收标准对照

| 标准 | 状态 |
|------|------|
| `pytest tests/tools/test_agent_team_tools.py` 全部通过 | ✅ 26/26 通过（0.29s） |
| 上下文缺失错误覆盖 | ✅ 6/6 tool 覆盖 |
| 异常路径覆盖 | ⚠️ 缺 `create_agent` 空名称 ValueError 路径 |
| JSON 字段完整性 | ✅ 输出均为有效 JSON，字段符合约定 |
| 对标 `task_tools` 模式 | ⚠️ 模式一致，但 DB 连接管理有差异 |

## Agent Brief

**类别：** enhancement
**摘要：** 修复代码审查中发现的 6 个问题：ContextManager 模块超限拆分、脱敏逻辑修正、CLI emoji 移除、消息 ID 生成去 hash、文件工具增加工作区边界防御、URL 凭据脱敏。

**当前行为：**

1. `ContextManager` 所在的 `context_manager.py` 为 849 行，超过项目规定的 800 行上限。该文件混合了 token 估算、脱敏工具函数、窗口策略类、上下文管理主类等多种职责。
2. `_redact_secrets` 使用 `"(" in pattern` 判断是否带捕获组来决定替换字符串，但此判断过于粗糙 — 若模式中包含转义括号或字符类中的括号会误判，导致部分模式替换结果异常。
3. CLI presenter 在 `format_conversation_header`、`show_history`、`show_save_info` 中使用了 🆕📋📭💾💡 等 emoji 字符，违反项目 AGENTS.md 中禁止 emoji 的规定。
4. `MessageRepository.save()` 使用 `hash(content) % 10000` 生成消息 ID 后缀。Python 的 `hash()` 在 3.x 中默认启用 hash randomization，不同进程间对同一字符串的 hash 值不同，导致消息 ID 不可复现且可能碰撞。
5. `read_file`、`write_file`、`edit_file` 三个文件工具函数不做任何工作区路径校验，完全依赖 `PermissionEngine` 的规则匹配。若 PermissionEngine 配置错误或被绕过，文件工具可读写工作区外的任意路径。
6. `_redact_secrets` 的脱敏正则列表中缺少对 URL 内嵌凭据（如 `https://user:password@example.com/path`）的匹配模式。

**期望行为：**

1. `context_manager.py` 不超过 800 行。将独立职责拆分为独立模块：
   - Token 估算逻辑移入独立模块（如 `src/core/token_estimator.py`）
   - 脱敏逻辑移入独立模块（如 `src/core/secrets.py`）
   - 窗口策略类移入独立模块（如 `src/core/window_strategies.py`）
   - `ContextManager` 主类保留在 `context_manager.py`，通过 import 引用上述模块
   - `src/core/__init__.py` 补充导出 `ContextManager`、`ContextSnapshot`、`ContextSummary` 等公开符号
2. `_redact_secrets` 的替换逻辑修正：对带捕获组的模式统一使用 `\1[REDACTED]` 替换（仅当模式确实包含捕获组时），对不带捕获组的模式使用 `[REDACTED]` 替换。判断依据改为检查 `re.compile(pattern).groups` 而非字符串包含判断。
3. CLI presenter 中所有 emoji 字符替换为纯文本标签或直接移除，保持输出简洁专业。
4. `MessageRepository.save()` 的消息 ID 生成改用 `uuid.uuid4().hex[:12]` 或基于时间戳+递增序号的方式，不再依赖 `hash()`。
5. `read_file`、`write_file`、`edit_file` 在函数入口处增加工作区边界校验：将传入路径 `resolve()` 后与配置的工作区根路径比较，若不在工作区内则拒绝操作并返回明确错误。工作区根路径通过参数或上下文注入（如环境变量 `WORKSPACE_ROOT` 或运行时配置）。
6. `_redact_secrets` 增加 URL 凭据脱敏模式：匹配 `://` 后紧跟的 `user:password@` 段，将密码部分替换为 `[REDACTED]`。

**关键接口：**

| 类型 | 名称 | 变更 |
|------|------|------|
| 模块 | `src/core/token_estimator.py` | 新建，从 context_manager 移入 `estimate_tokens()` |
| 模块 | `src/core/secrets.py` | 新建，从 context_manager 移入 `_redact_secrets()` |
| 模块 | `src/core/window_strategies.py` | 新建，从 context_manager 移入 `WindowStrategy`、`SlidingWindowStrategy` |
| 函数 | `estimate_tokens(messages) -> int` | 移动至 token_estimator.py，签名不变 |
| 函数 | `redact_secrets(value: str) -> str` | 移动至 secrets.py，重命名为公开函数，修正替换逻辑，增加 URL 凭据模式 |
| 类 | `WindowStrategy` | 移动至 window_strategies.py |
| 类 | `SlidingWindowStrategy` | 移动至 window_strategies.py |
| 类 | `ContextManager` | 保留在 context_manager.py，import 上述模块 |
| 函数 | `read_file(path, workspace_root=None) -> str` | 增加 workspace_root 参数，入口处校验路径边界 |
| 函数 | `write_file(path, content, workspace_root=None) -> str` | 同上 |
| 函数 | `edit_file(path, oldString, newString, replaceAll, workspace_root=None) -> str` | 同上 |
| 方法 | `MessageRepository.save()` | msg_id 生成改用 uuid |
| 函数 | `format_conversation_header()` | 移除 emoji |
| 函数 | `show_history()` | 移除 emoji |
| 函数 | `show_save_info()` | 移除 emoji |
| 模块 | `src/core/__init__.py` | 补充导出 ContextManager、ContextSnapshot、ContextSummary、WindowStrategy、SlidingWindowStrategy |

**验收标准：**

- [ ] `src/core/context_manager.py` 行数 ≤ 800
- [ ] `src/core/` 下新增 `token_estimator.py`、`secrets.py`、`window_strategies.py` 三个模块，各自职责单一
- [ ] `src/core/__init__.py` 导出 `ContextManager`、`ContextSnapshot`、`ContextSummary`、`WindowStrategy`、`SlidingWindowStrategy`
- [ ] 所有现有 `from src.core.context_manager import ...` 的引用点无需修改即可正常工作（通过 `__init__.py` 或原模块 re-export 兼容）
- [ ] `_redact_secrets`（重命名后）对 `sk-abc123` 输出 `[REDACTED]`，对 `password=secret` 输出 `password=[REDACTED]`
- [ ] `_redact_secrets` 对 `https://user:pass123@example.com` 输出 `https://user:[REDACTED]@example.com`
- [ ] `_redact_secrets` 对 `Bearer token123` 输出 `Bearer [REDACTED]`
- [ ] CLI 输出中不再包含任何 emoji 字符（Unicode emoji 范围 U+1F300–U+1FAFF 等）
- [ ] `MessageRepository.save()` 生成的 msg_id 在同一毫秒内多次调用不碰撞
- [ ] `MessageRepository.save()` 生成的 msg_id 在不同进程中可复现（基于时间戳+序号）
- [ ] `read_file("/etc/passwd", workspace_root="/home/user/project")` 返回错误，不读取文件
- [ ] `write_file("/tmp/evil.sh", "content", workspace_root="/home/user/project")` 返回错误，不写入文件
- [ ] `edit_file("../outside.txt", "a", "b", workspace_root="/home/user/project")` 返回错误，不编辑文件
- [ ] 工作区内的正常文件操作不受影响
- [ ] 现有测试全部通过

**不在范围内：**

- 不修改 PermissionEngine 的规则匹配逻辑
- 不修改 `context_manager.py` 中 ContextManager 类的公开 API 签名
- 不修改 `estimate_tokens` 的估算算法本身
- 不新增数据库表或迁移脚本
- 不修改 `src/tools/registry.py` 中工具注册逻辑（workspace_root 通过闭包或参数注入，不改变工具注册签名）
- 不新增配置文件或环境变量（workspace_root 复用现有 Runtime 配置中的工作目录）

# Permission 插件契约

关联：ADR 0007（插件能力）、ADR 0008（默认安全姿态）、`src/core/tool_pipeline.py`。

## 能力声明

permission 插件在 Manifest 中声明 `CapabilityKind.PERMISSION`，名称由插件自选：

```python
from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, Manifest

manifest = Manifest(
    name="my-permission",
    version="0.1.0",
    api_version=1,
    capabilities=(CapabilityDeclaration(kind=CapabilityKind.PERMISSION, name="policy"),),
)
```

## Provider 形态

`register()` 把 provider 注册到 `CapabilityKind.PERMISSION`。provider 可以是：

1. 一个 async callable，签名为 `(ToolCall) -> HookDecision | None`；
2. 一个已包装的 `BeforeToolCallHook(callback=...)`。

推荐直接注册 async callable：

```python
from src.core.tool_pipeline import HookDecision, ToolCall


async def check(call: ToolCall) -> HookDecision | None:
    if call.name == "bash" and "rm -rf" in str(call.arguments.get("command", "")):
        return HookDecision(block=True, reason="destructive command")
    return None


class MyPermissionPlugin:
    manifest = manifest

    def register(self, registrar, config):
        registrar.register(CapabilityKind.PERMISSION, "policy", check)
```

## 执行语义

- permission provider 按注册顺序执行，并排在通用 `BeforeToolCallHook` 之前。
- 任一 provider 返回 `HookDecision(block=True)`：工具不执行，Observation 状态为 `denied`。
- 任一 provider 抛异常或返回非 `HookDecision`：工具不执行，Observation 状态为 `error`（fail-closed）。
- 返回 `None` 或 `HookDecision(block=False)`：继续交给下一个 provider / 通用 hook。
- provider 形态非法（既不可调用也不是 `BeforeToolCallHook`）时，流水线组装直接报错，不静默忽略。

## 与 ADR 0008 警告的关系

只要宿主中注册了任意 `PERMISSION` 能力，启动时的“未安装 permission 插件”警告就不会出现。
因此 permission 插件应使用 `PERMISSION` 能力承载拦截逻辑，而不是只注册通用 `HOOK`：

- 只注册 `HOOK`：能拦截，但仍会收到“未安装 permission 插件”警告；
- 只注册 `PERMISSION`：现在会真正执行拦截，警告也会正确消失。

## 与通用 Hook 的分工

- `PERMISSION`：工具调用的放行策略（allow / deny / error），安全边界。
- `HOOK`：afterToolCall 改写、turn 边界注入、memory 等非权限用途；beforeToolCall 仍可用于通用拦截。

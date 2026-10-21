# ADR 0007: 插件化架构

## 状态

已决策，随 2026-10 重构实施（`docs/2026-10-21-plugin-refactor-plan.md`）。

## 背景

旧架构中工具、权限、记忆等能力以固定模块存在（`src/tools/`、`src/permission/`、`src/memory/`），每加一种能力都要改内核注册链路；memory 甚至只留了 Protocol 死代码。本次全面重构（替换 GUI、配置改 YAML）同时收敛能力面，需要一个能承载"能力即扩展"的宿主结构。

## 决策

内核只保留 Engine、hook 管线与插件宿主（PluginHost），一切能力以**插件**形式注册：

- **契约**：Manifest（名称、版本、`api_version`、能力清单、配置 schema）+ Plugin Protocol。内核只加载 `api_version` 兼容的插件。
- **发现**：Entry Points 是第三方插件的唯一发现入口；内置插件（read/write/bash/edit/grep、mcp、skill、storage）与外部插件走同一契约，区别仅在发现方式。
- **能力分类**：插件是**能力包**——一个插件可同时注册多种能力（tool / hook / permission / storage）。
- **LLM 例外**（已被 ADR 0011 取代）：litellm 统一接入多 provider，归内核，不设 LLM 插件能力；ADR 0011 改为 provider 配置 + 原生协议适配器。
- **memory 不设专用能力接口**：memory 外部插件通过 hooks（上下文注入）+ tools（读写）组合实现，避免为无实现的能预留接口。

## 被否决的方案

- **进程内注册表、无 entry points**（第三方扩展性不足）。
- **进程外插件（MCP 化）**：隔离最好但开销与调试成本过高，教学项目不值得。
- **storage 归内核**：存储被选为内置插件，保持"能力皆插件"的一致性；但不抽象多后端，仍用 SQLAlchemy/SQLite。
- **memory 专用 MemoryProvider 能力**：YAGNI，等第一个真实 memory 插件出现再考虑进协议。

## 后果

- Entry Points 发布即产生兼容性承诺，插件协议变更必须走 `api_version` 升级。
- 插件缺席 = 能力缺席，内核不做隐式兜底（安全侧后果见 ADR 0008）。

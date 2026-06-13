## Agent Brief

**类别：** enhancement
**摘要：** 废弃所有旧配置文件支持，项目仅从 `intelliagent.json` 加载配置

**当前行为：**
仓库中仍遗留以下旧配置文件及对应代码：
- `permissions.json` — 权限规则，已可通过 `intelliagent.json` 的 `permissions.rules` 配置
- `.env.example` — 环境变量示例，已由 `intelliagent.json.example` 替代
- `mcp_config.example.json` — MCP 示例配置，已合并到 `intelliagent.json` 的 `mcp.servers`
- `MCPConfig.from_file()` — 旧加载方法，无任何调用方

文档 `docs/config-unification-design.md` 和 `docs/2026-06-13-issue-8-config-unification-brief.md` 中仍描述向后兼容策略。

**期望行为：**
- 旧配置文件从版本控制中删除（`git rm`）
- `MCPConfig.from_file()` 方法移除
- 文档中所有提及向后兼容/旧配置的内容更新为"仅支持 intelliagent.json"
- `.gitignore` 确保旧文件模式被忽略
- 所有测试通过

**关键接口：**
- `MCPConfig.from_file(path)` — 删除。无任何调用方，`from_unified_config()` 和 `from_dict()` 保留
- `DEFAULT_RULES` — 保留，用于 intelliagent.json 中未配置权限规则时的默认值

**验收标准：**
- [ ] `permissions.json`、`.env.example`、`mcp_config.example.json` 已从版本控制中删除
- [ ] `MCPConfig.from_file()` 方法已移除
- [ ] 全部测试通过（231 passed, 7 skipped）
- [ ] `grep -r` 无代码引用已删除的旧配置文件路径
- [ ] 文档 `docs/config-unification-design.md` 和 `docs/2026-06-13-issue-8-config-unification-brief.md` 中的向后兼容描述已修正
- [ ] `.gitignore` 已更新，忽略旧配置文件模式

**不在范围内：**
- 不修改 `intelliagent.json` 的 schema 或配置模型
- 不修改测试逻辑（测试无需适配旧配置，测试已全量使用新配置）
- 不删除 `DEFAULT_RULES` 硬编码默认值（作为未配置时的 fallback 保留）
- 不修改 `load_permission_engine()` 签名

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues (`devcxl/intelliagent`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: one `CONTEXT.md` + `docs/adr/` at repo root. See `docs/agents/domain.md`.

## Coding Agent Architecture

IntelliAgent is a coding-agent skeleton, not a web application. Its architecture should stay close to the mental model used by Claude Code, Codex, and OpenCode: a small agent loop reads context, asks the model for the next step, executes explicit tools, records observations, and repeats until the model returns a final answer or a safety guard stops the run.

### Design Principles

- Keep the architecture explainable in one pass: each top-level package must have one obvious responsibility.
- Preserve a clear seam between orchestration and adapters: `src/core/` owns the agent loop and plugin host; `src/plugins/` implements capabilities behind the plugin contract; `src/llm/` adapts model providers; `src/runtime/` wires concrete dependencies; `src/config/` reads settings; storage persists entries via the storage plugin.
- Treat tools as constrained adapters, not hidden business logic. Every tool must have a small schema, predictable JSON response, and permission check before side effects.
- Keep the model-visible loop transparent: prompts, tool calls, observations, safety stops, and final answers should be easy to inspect and test.
- Prefer explicit data flow over global state. Runtime assembly may create concrete objects; core modules should receive dependencies through their constructor.
- Avoid ambiguous names. Use agent-domain terms consistently: `Run`, `Conversation`, `Trace`, `Tool`, `Observation`, `Permission`, `Runtime`, and `Engine`.
- Do not add framework-shaped layers unless they earn their interface. A module is justified only when it improves locality or provides leverage behind a small interface.
- Optimize for human review and hiring demonstration: small files, direct control flow, minimal abstractions, strong tests around seams, and no speculative features.

### Directory Intent

- `src/core/`: Engine loop, plugin host, tool pipeline, compaction. No provider-specific setup and no persistence ownership.
- `src/plugins/`: Built-in plugins (basic_tools, mcp, skill, storage). Same contract as external plugins.
- `src/llm/`: litellm-based model access. No agent-loop policy.
- `src/runtime/`: Composition root (config → PluginHost → Engine).
- `src/config/`: YAML settings only.
- `src/tui/` + `src/headless/`: Frontends consuming the engine event stream only.
- `tests/`: Verify public seams with fakes before relying on real providers.

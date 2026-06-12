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
- Preserve a clear seam between orchestration and adapters: `src/core/` owns the agent loop and safety rules; `src/llm/` adapts model providers; `src/tools/` exposes executable tools; `src/runtime/` wires concrete dependencies; `src/config/` reads settings; `src/db/` persists runs, messages, and traces.
- Treat tools as constrained adapters, not hidden business logic. Every tool must have a small schema, predictable JSON response, and permission check before side effects.
- Keep the model-visible loop transparent: prompts, tool calls, observations, safety stops, and final answers should be easy to inspect and test.
- Prefer explicit data flow over global state. Runtime assembly may create concrete objects; core modules should receive dependencies through their constructor.
- Avoid ambiguous names. Use agent-domain terms consistently: `Run`, `Conversation`, `Trace`, `Tool`, `Observation`, `Permission`, `Runtime`, and `Engine`.
- Do not add framework-shaped layers unless they earn their interface. A module is justified only when it improves locality or provides leverage behind a small interface.
- Optimize for human review and hiring demonstration: small files, direct control flow, minimal abstractions, strong tests around seams, and no speculative features.

### Directory Intent

- `src/core/`: ReAct engine, safety checks, permission decisions. No provider-specific setup and no persistence ownership.
- `src/llm/`: LLM provider client adapters. No agent-loop policy.
- `src/tools/`: Built-in tool implementations and tool schema registry. No runtime assembly.
- `src/runtime/`: Composition root for settings, LLM client, permissions, and engine creation.
- `src/db/`: Persistence for conversations, messages, runs, and traces.
- `src/config/`: Typed settings only.
- `tests/`: Verify public seams with fakes before relying on real providers.

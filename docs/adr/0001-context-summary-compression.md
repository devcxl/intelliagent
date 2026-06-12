# ADR 0001: Context Summary Compression

## Status

Accepted

## Context

IntelliAgent is a coding-agent skeleton. Its context management must stay simple, explicit, and reviewable while still matching the mental model of coding agents such as Claude Code, Codex, and OpenCode.

The current context strategy can preserve protocol legality, but it still behaves like a sliding window: old raw messages may be dropped when the context grows. That has two problems:

- Dropping raw messages can lose useful task state.
- Keeping a moving suffix of raw messages makes prompt shape less stable and can reduce cache usefulness.

We want a clearer rule: preserve the instruction prefix exactly, and compress the mutable conversation state when the context grows too large.

## Decision

Introduce automatic context compression with a `ContextSummary`.

When estimated context usage reaches 75% of the configured context window, `ContextManager` will compress all non-instruction messages into one summary message.

After compression, the model-visible context becomes:

```text
system prompt
agent prompt
tools instruction
context summary message
```

No raw conversation, assistant, or tool messages are kept after compression. The compressed summary must contain the active task state, relevant facts, completed actions, tool observations, pending work, and the next suggested step.

## Instruction Prefix

The first part of the context is a stable instruction prefix. It must preserve these instruction sources as separate ordered blocks:

```text
system prompt
agent prompt
tools instruction
```

These instruction sources are not summarized and are not dropped by context compression.

The order is deterministic:

```text
1. system prompt
2. agent prompt
3. tools instruction
```

The instruction blocks are not merged into one synthetic prompt. Keeping them separate makes the model-visible structure easier to inspect and preserves the intended responsibilities of each prompt layer.

## Summary Message

The summary message appears after the instruction prefix. It is a normal model-visible message, not a tool message.

Preferred role:

```python
{"role": "user", "content": "以下是已压缩的上下文摘要：\n..."}
```

The summary message must include these sections:

```text
当前目标:
- ...

用户约束:
- ...

已完成动作:
- ...

关键观察:
- ...

涉及文件:
- ...

待处理事项:
- ...

下一步建议:
- ...
```

The summary must explicitly preserve the current user task. If the current task is not present in the summary, compression is invalid.

## Trigger Rule

Compression is automatic.

```text
if estimated_context_tokens >= max_context_tokens * 0.75:
    compact_to_summary()
```

The token estimate may be approximate. Actual provider usage can be used later to improve the estimate, but the first implementation should remain deterministic and testable.

## Compression Scope

Compress these message types:

- User task and follow-up messages
- Assistant responses
- Assistant tool call messages
- Tool observation messages
- Safety warning messages

Do not compress these instruction sources:

- System prompt
- Agent prompt
- Tools instruction

Do not keep raw non-instruction messages after compression.

## Protocol Safety

Compression must not emit `tool` messages. Tool observations should be represented as plain text inside the summary.

This avoids invalid OpenAI function-calling states such as a `tool` message without a preceding `assistant.tool_calls` message.

## Deterministic First Version

The first implementation should not call an LLM to summarize.

The initial summarizer should be deterministic:

- Convert user messages into task/constraint bullets.
- Convert assistant text into completed-action or answer bullets.
- Convert tool calls and tool results into observation bullets.
- Truncate long content per bullet.
- Limit total summary length.

LLM-based summarization may be added later behind a separate seam, but it is not part of this decision.

## ContextManager API Shape

Expected concepts:

```python
@dataclass
class ContextSummary:
    content: str
    source_message_count: int
    compression_count: int


class ContextManager:
    def initialize_instructions(
        self,
        system_prompt: str,
        agent_prompt: str,
        tools_instruction: str,
    ) -> None: ...
    def compact_if_needed(self) -> bool: ...
    def compact_to_summary(self) -> ContextSummary: ...
    def get_messages(self) -> list[dict[str, Any]]: ...
```

`ReactEngine` should not know how summary text is produced. It should provide the instruction blocks and call `ContextManager.compact_if_needed()` before LLM calls.

## Consequences

Positive:

- Context shape is simple: stable instruction prefix plus one compressed state message.
- Cache behavior is more predictable because the instruction prefix is preserved exactly.
- No invalid tool-call protocol can survive compression.
- The model receives explicit current state rather than an arbitrary recent suffix.

Negative:

- Deterministic summaries may lose details from large tool outputs.
- Compression changes the second message, so cache hits after compression are still affected.
- Summary quality becomes a correctness concern and must be tested.

## Verification Requirements

Implementation must include tests for:

- Compression triggers at 75% estimated context usage.
- The instruction prefix preserves system prompt, agent prompt, and tools instruction exactly and in order.
- After compression, only the instruction prefix and one summary message remain.
- Raw assistant/tool/user history is not retained outside the summary.
- The current task appears in the summary.
- Tool observations are represented as text, not `tool` role messages.
- A second compression updates the existing summary instead of adding another summary message.

## Non-Goals

- No vector database.
- No long-term memory system.
- No background summarization worker.
- No LLM summarizer in the first implementation.
- No provider-specific prompt-cache logic in `core`.

from __future__ import annotations

from src.core.context_manager import ContextManager, SlidingWindowStrategy


def test_compact_if_needed_replaces_raw_messages_with_instruction_prefix_and_summary():
    ctx = ContextManager(
        system_prompt="system prompt",
        agent_prompt="agent prompt",
        tools_instruction="tools instruction",
        max_tokens=80,
    )
    ctx.initialize("当前任务")
    ctx.add_assistant_message("已完成第一步" + "x" * 80)

    compacted = ctx.compact_if_needed()

    assert compacted is True
    messages = ctx.get_messages()
    assert messages[:3] == [
        {"role": "system", "content": "system prompt"},
        {"role": "system", "content": "agent prompt"},
        {"role": "system", "content": "tools instruction"},
    ]
    assert len(messages) == 4
    assert messages[3]["role"] == "user"
    assert "以下是已压缩的上下文摘要" in messages[3]["content"]
    assert "当前任务" in messages[3]["content"]
    assert "已完成第一步" in messages[3]["content"]


def test_compact_if_needed_uses_75_percent_boundary():
    ctx = ContextManager(max_tokens=100)
    ctx.initialize("当前任务")
    ctx.estimate_tokens = lambda: 74

    assert ctx.compact_if_needed(max_tokens=100) is False

    ctx.estimate_tokens = lambda: 75
    assert ctx.compact_if_needed(max_tokens=100) is True


def test_compact_if_needed_includes_extra_token_budget():
    ctx = ContextManager(max_tokens=100)
    ctx.initialize("当前任务")
    ctx.estimate_tokens = lambda: 70

    assert ctx.compact_if_needed(max_tokens=100, extra_tokens=4) is False
    assert ctx.compact_if_needed(max_tokens=100, extra_tokens=5) is True


def test_compact_summary_contains_tool_observation_without_tool_role_message():
    ctx = ContextManager(
        system_prompt="system prompt",
        agent_prompt="agent prompt",
        tools_instruction="tools instruction",
        max_tokens=80,
    )
    ctx.initialize("读取配置")
    ctx.add_assistant_message(
        None,
        [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"pyproject.toml"}'},
            }
        ],
    )
    ctx.add_tool_message("call-1", '{"status":"ok","result":"project=intelliagent"}')

    ctx.compact_to_summary()

    messages = ctx.get_messages()
    assert all(msg["role"] != "tool" for msg in messages)
    summary = messages[-1]["content"]
    assert "工具调用 read_file" in summary
    assert "pyproject.toml" in summary
    assert "project=intelliagent" in summary


def test_compact_summary_redacts_common_secrets_from_tool_observations():
    ctx = ContextManager(
        system_prompt="system prompt",
        agent_prompt="agent prompt",
        tools_instruction="tools instruction",
        max_tokens=80,
    )
    ctx.initialize("读取环境变量")
    ctx.add_tool_message("call-secret", "password=hunter2 api_key=secret sk-live-token")

    ctx.compact_to_summary()

    summary = ctx.get_messages()[-1]["content"]
    assert "hunter2" not in summary
    assert "api_key=secret" not in summary
    assert "sk-live-token" not in summary
    assert "[REDACTED]" in summary


def test_compact_summary_keeps_assistant_content_when_tool_calls_exist():
    ctx = ContextManager(
        system_prompt="system prompt",
        agent_prompt="agent prompt",
        tools_instruction="tools instruction",
        max_tokens=80,
    )
    ctx.initialize("读取配置")
    ctx.add_assistant_message(
        "我需要先读取项目配置",
        [
            {
                "id": "call-1",
                "type": "function",
                "function": {"name": "read_file", "arguments": '{"path":"pyproject.toml"}'},
            }
        ],
    )

    ctx.compact_to_summary()

    summary = ctx.get_messages()[-1]["content"]
    assert "我需要先读取项目配置" in summary
    assert "工具调用 read_file" in summary


def test_second_compaction_updates_existing_summary_message():
    ctx = ContextManager(
        system_prompt="system prompt",
        agent_prompt="agent prompt",
        tools_instruction="tools instruction",
        max_tokens=80,
    )
    ctx.initialize("当前任务")
    ctx.add_assistant_message("第一次完成")
    first_summary = ctx.compact_to_summary()

    ctx.add_assistant_message("第二次完成")
    second_summary = ctx.compact_to_summary()

    messages = ctx.get_messages()
    summary_messages = [
        msg for msg in messages
        if msg["role"] == "user" and msg["content"].startswith("以下是已压缩的上下文摘要")
    ]
    assert len(summary_messages) == 1
    assert first_summary.compression_count == 1
    assert second_summary.compression_count == 2
    summary = summary_messages[0]["content"]
    assert "第一次完成" in summary
    assert "第二次完成" in summary
    assert summary.count("第一次完成") == 1


def test_to_dict_from_dict_preserves_instruction_prefix_and_summary():
    ctx = ContextManager(
        system_prompt="system prompt",
        agent_prompt="agent prompt",
        tools_instruction="tools instruction",
        max_tokens=80,
    )
    ctx.initialize("当前任务")
    ctx.add_assistant_message("完成动作")
    ctx.compact_to_summary()

    restored = ContextManager.from_dict(ctx.to_dict())

    messages = restored.get_messages()
    assert messages[:3] == [
        {"role": "system", "content": "system prompt"},
        {"role": "system", "content": "agent prompt"},
        {"role": "system", "content": "tools instruction"},
    ]
    assert restored.summary is not None
    assert "当前任务" in restored.summary.content


def test_initialize_builds_system_and_history_aware_user_message():
    ctx = ContextManager(
        system_prompt="system",
        agent_prompt="",
        tools_instruction="",
    )

    ctx.initialize("当前任务", history_context="历史摘要")

    messages = ctx.get_messages()
    assert messages[0] == {"role": "system", "content": "system"}
    assert messages[1]["role"] == "user"
    assert "历史摘要" in messages[1]["content"]
    assert "现在的新任务是：当前任务" in messages[1]["content"]
    assert "请结合上述对话历史" in messages[1]["content"]


def test_build_history_context_limits_messages_and_content():
    history = [
        {"role": "user", "content": "早期"},
        {"role": "assistant", "content": "x" * 20},
    ]

    context = ContextManager.build_history_context(
        history,
        max_messages=1,
        max_content_length=5,
    )

    assert context is not None
    assert "早期" not in context
    assert "[ASSISTANT] xxxxx..." in context


def test_truncate_keeps_tool_call_group_together():
    ctx = ContextManager(
        system_prompt="system",
        window_strategy=SlidingWindowStrategy(min_messages=2),
        max_tokens=80,
    )
    ctx.initialize("原始任务")
    ctx.add_assistant_message(
        "old" + "x" * 100,
        [{"id": "old-call", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
    )
    ctx.add_tool_message("old-call", "old-result" + "x" * 100)
    ctx.add_assistant_message(
        "new" + "y" * 20,
        [{"id": "new-call", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}],
    )
    ctx.add_tool_message("new-call", "new-result")

    messages = ctx.truncate(max_tokens=80)

    tool_call_ids = {
        tc["id"]
        for msg in messages
        for tc in msg.get("tool_calls", [])
    }
    tool_message_ids = {
        msg["tool_call_id"]
        for msg in messages
        if msg.get("role") == "tool"
    }
    assert tool_message_ids <= tool_call_ids
    assert "new-call" in tool_call_ids
    assert "new-call" in tool_message_ids


def test_truncate_drops_orphan_tool_message():
    ctx = ContextManager(
        system_prompt="system",
        window_strategy=SlidingWindowStrategy(min_messages=1),
        max_tokens=80,
    )
    ctx.initialize("原始任务")
    ctx.add_tool_message("orphan-call", "orphan-result")
    ctx.add_user_message("后续任务" + "x" * 100)

    messages = ctx.truncate(max_tokens=80)

    assert all(msg.get("role") != "tool" for msg in messages)

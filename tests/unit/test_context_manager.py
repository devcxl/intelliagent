from __future__ import annotations

from src.core.context_manager import ContextManager, ContextSummary


def _make_cm(max_tokens: int = 1000) -> ContextManager:
    cm = ContextManager(max_context_tokens=max_tokens)
    cm.initialize_instructions(
        system_prompt="你是 coding agent",
        agent_prompt="你擅长 Python",
        tools_instruction="可用工具：read_file、write_file",
    )
    return cm


# ============================================================================
# 指令前缀
# ============================================================================


def test_instruction_prefix_preserved():
    cm = _make_cm()
    msgs = cm.get_messages()
    assert len(msgs) == 3
    assert msgs[0] == {"role": "system", "content": "你是 coding agent"}
    assert msgs[1] == {"role": "system", "content": "你擅长 Python"}
    assert msgs[2] == {"role": "system", "content": "可用工具：read_file、write_file"}


def test_instruction_prefix_order():
    cm = _make_cm()
    msgs = cm.get_messages()
    assert msgs[0]["content"] == "你是 coding agent"
    assert msgs[1]["content"] == "你擅长 Python"
    assert msgs[2]["content"] == "可用工具：read_file、write_file"


# ============================================================================
# 消息添加
# ============================================================================


def test_add_messages():
    cm = _make_cm()
    cm.add_user_message("帮助我重构代码")
    cm.add_assistant_message("好的，我来看看")
    cm.add_tool_message("call_1", "文件读取成功")

    msgs = cm.get_messages()
    assert len(msgs) == 6
    assert msgs[3] == {"role": "user", "content": "帮助我重构代码"}
    assert msgs[4] == {"role": "assistant", "content": "好的，我来看看"}
    assert msgs[5] == {"role": "tool", "tool_call_id": "call_1", "content": "文件读取成功"}


def test_assistant_with_tool_calls():
    cm = _make_cm()
    tc = [{"id": "call_1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "x.py"}'}}]
    cm.add_assistant_message(content=None, tool_calls=tc)
    msgs = cm.get_messages()
    assert msgs[3]["role"] == "assistant"
    assert msgs[3]["tool_calls"] == tc


# ============================================================================
# 压缩触发阈值
# ============================================================================


def test_compact_not_triggered_below_threshold():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("hi")
    result = cm.compact_if_needed(estimated_tokens=70)
    assert result is None, "70 < 100*0.75=75，不应触发"


def test_compact_triggered_at_75_percent():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("hi")
    result = cm.compact_if_needed(estimated_tokens=80)
    assert result is not None, "80 >= 75，应触发"
    assert isinstance(result, ContextSummary)


# ============================================================================
# 压缩后上下文形状
# ============================================================================


def test_compact_only_prefix_and_summary():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("重构文件 x.py")
    cm.add_assistant_message("好的，我来读取")
    cm.add_tool_message("call_1", "文件内容：def foo(): pass")

    cm.compact_if_needed(estimated_tokens=80)
    msgs = cm.get_messages()

    assert len(msgs) == 4, "3 instruction + 1 summary"
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "system"
    assert msgs[2]["role"] == "system"
    assert msgs[3]["role"] == "user"
    assert "摘要" in msgs[3]["content"] or "重构" in msgs[3]["content"]


def test_no_raw_messages_after_compact():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("重构文件 x.py")
    cm.add_assistant_message("好的")
    cm.add_tool_message("call_1", "内容")

    cm.compact_if_needed(estimated_tokens=80)
    msgs = cm.get_messages()

    roles = [m["role"] for m in msgs]
    assert roles == ["system", "system", "system", "user"]


def test_no_tool_role_after_compact():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("hi")
    cm.add_assistant_message(
        content=None,
        tool_calls=[{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
    )
    cm.add_tool_message("c1", "result")

    cm.compact_if_needed(estimated_tokens=80)
    msgs = cm.get_messages()

    for m in msgs:
        assert m["role"] != "tool"


# ============================================================================
# 第二次压缩更新 summary
# ============================================================================


def test_second_compact_updates_summary():
    cm = _make_cm(max_tokens=100)

    cm.add_user_message("任务1")
    cm.add_assistant_message("完成1")
    cm.compact_if_needed(estimated_tokens=80)

    cm.add_user_message("任务2")
    cm.add_assistant_message("完成2")
    cm.compact_if_needed(estimated_tokens=80)

    msgs = cm.get_messages()
    assert len(msgs) == 4, "只有一条 summary，不追加第二条"
    assert msgs[3]["content"].count("摘要") == 1 or "任务2" in msgs[3]["content"]


def test_second_compact_does_not_append_second_summary():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("任务1")
    cm.add_assistant_message("完成1")
    cm.compact_if_needed(estimated_tokens=80)

    cm.add_user_message("任务2")
    cm.compact_if_needed(estimated_tokens=80)

    msgs = cm.get_messages()
    summary_count = sum(1 for m in msgs if m["role"] == "user")
    assert summary_count == 1


# ============================================================================
# 当前任务在 summary 中
# ============================================================================


def test_current_task_in_summary():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("修复日志模块的 bug")
    cm.add_assistant_message("找到 bug：空指针")
    cm.add_tool_message("call_1", "修复完成")
    cm.add_assistant_message("已修复")

    cm.compact_if_needed(estimated_tokens=80)
    msgs = cm.get_messages()

    summary = msgs[3]["content"]
    assert "bug" in summary or "日志" in summary or "修复" in summary


# ============================================================================
# 不调用 LLM
# ============================================================================


def test_compact_does_not_call_llm():
    cm = _make_cm(max_tokens=100)
    cm.add_user_message("hi")
    cm.add_assistant_message("hello")
    cm.compact_if_needed(estimated_tokens=80)
    # ContextManager 本身不持有 LLM client，能跑就说明没有 LLM 依赖


# ============================================================================
# load_history + compact
# ============================================================================


def test_load_history_then_compact():
    cm = _make_cm(max_tokens=100)
    cm.load_history(
        [
            {"role": "user", "content": "历史消息1"},
            {"role": "assistant", "content": "回复1"},
            {"role": "tool", "tool_call_id": "c1", "content": "结果1"},
            {"role": "assistant", "content": "最终回复"},
        ]
    )
    result = cm.compact_if_needed(estimated_tokens=80)
    assert result is not None
    msgs = cm.get_messages()
    assert len(msgs) == 4

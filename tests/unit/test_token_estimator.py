from __future__ import annotations

from src.core.token_estimator import estimate_tokens


def test_estimate_tokens_empty():
    assert estimate_tokens([]) == 0


def test_estimate_tokens_single_message():
    msgs = [{"role": "user", "content": "hello"}]
    total = estimate_tokens(msgs)
    assert total > 0
    # 4 overhead + len("hello") * 1.3
    assert total == 4 + int(5 * 1.3)


def test_estimate_tokens_with_tool_calls():
    msgs = [
        {"role": "assistant", "content": "let me check", "tool_calls": [{"id": "1"}]},
    ]
    total = estimate_tokens(msgs)
    content_cost = int(len("let me check") * 1.3)
    assert total == 4 + content_cost + 10


def test_estimate_tokens_multiple_messages():
    msgs = [
        {"role": "system", "content": "you are a helper"},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello!", "tool_calls": [{"id": "1"}, {"id": "2"}]},
    ]
    total = estimate_tokens(msgs)
    content_costs = sum(int(len(str(m.get("content", ""))) * 1.3) for m in msgs)
    assert total == 3 * 4 + content_costs + 20

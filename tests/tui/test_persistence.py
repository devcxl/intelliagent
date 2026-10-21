"""TUI 持久化接线：重启后自动续接同一数据库中的 tui 会话。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.tui.assembly import build_app
from tests.core.engine_support import FakeLLM, text_events
from tests.tui.conftest import submit

TUI_CONFIG = """\
default_model: fake/model
providers:
  fake:
    type: openai-compatible
    api: http://127.0.0.1:9/v1
    models:
      model:
        limit:
          context: 1000000
workspace:
  dir: .
plugins:
  storage:
    config:
      database_url: {database_url}
"""


async def test_tui_resumes_tui_conversation_after_restart(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "tui.db"
    config = tmp_path / "intelliagent.yaml"
    config.write_text(TUI_CONFIG.format(database_url=str(database)), encoding="utf-8")

    first_llm = FakeLLM()
    first_llm.enqueue(*text_events("hi"))
    monkeypatch.setattr("src.tui.assembly.create_llm_client", lambda config: first_llm)
    first_app = build_app(config)
    async with first_app.run_test() as pilot:
        await submit(pilot, "hello")
        await first_app.workers.wait_for_complete()
        await pilot.pause()

    second_llm = FakeLLM()
    second_llm.enqueue(*text_events("again"))
    monkeypatch.setattr("src.tui.assembly.create_llm_client", lambda config: second_llm)
    second_app = build_app(config)
    async with second_app.run_test() as pilot:
        await submit(pilot, "next")
        await second_app.workers.wait_for_complete()
        await pilot.pause()

    assert [message.get("content") for message in second_llm.requests[0].messages] == [
        "hello",
        "hi",
        "next",
    ]

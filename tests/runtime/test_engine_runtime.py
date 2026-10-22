"""运行时接线：storage → Compactor → Engine，并验证 TUI 续接 / headless 新会话。"""

from __future__ import annotations

from pathlib import Path

from src.config.providers import Limits, ModelConfig, ProviderConfig
from src.config.yaml_config import IntelliAgentConfig
from src.core.plugin_host import PluginHost
from src.plugins.storage import StoragePlugin
from src.runtime.engine_runtime import build_engine_runtime
from tests.core.engine_support import FakeLLM, text_events


def build_config() -> IntelliAgentConfig:
    return IntelliAgentConfig(
        default_model="fake/model",
        providers={
            "fake": ProviderConfig(
                type="openai-compatible",
                api="http://127.0.0.1:9/v1",
                models={"model": ModelConfig(limit=Limits(context=1_000_000, output=4096))},
            )
        },
    )


def build_host(database: Path) -> PluginHost:
    host = PluginHost()
    host.load(StoragePlugin(), {"database_url": str(database)})
    return host


def non_system(messages):  # noqa: ANN001, ANN202 - 测试内联 helper
    return [message for message in messages if message.get("role") != "system"]


async def test_runtime_persists_and_resumes_tui_conversation(tmp_path: Path) -> None:
    config = build_config()
    host = build_host(tmp_path / "runtime.db")
    first_llm = FakeLLM()
    first_llm.enqueue(*text_events("hi"))
    first = build_engine_runtime(config, host, first_llm, "fake/model", None, conversation_id="tui", resume=True)
    try:
        await first.engine.run("hello")
        assert first.storage is not None
        leaf = await first.storage.latest_leaf_in("tui")
        _summary, kept = await first.storage.chat_projection(leaf)
        assert [message["content"] for _entry_id, message in kept] == ["hello", "hi"]

        second_llm = FakeLLM()
        second_llm.enqueue(*text_events("again"))
        second = build_engine_runtime(config, host, second_llm, "fake/model", None, conversation_id="tui", resume=True)
        try:
            await second.engine.run("next")
        finally:
            await second.close()

        messages = second_llm.requests[0].messages
        assert [message.get("content") for message in non_system(messages)] == ["hello", "hi", "next"]
    finally:
        await first.close()


async def test_runtime_new_headless_conversation_does_not_reuse_tui_context(tmp_path: Path) -> None:
    config = build_config()
    host = build_host(tmp_path / "runtime.db")
    tui_llm = FakeLLM()
    tui_llm.enqueue(*text_events("hi"))
    tui_runtime = build_engine_runtime(config, host, tui_llm, "fake/model", None, conversation_id="tui", resume=True)
    try:
        await tui_runtime.engine.run("hello")

        headless_llm = FakeLLM()
        headless_llm.enqueue(*text_events("done"))
        headless_runtime = build_engine_runtime(
            config,
            host,
            headless_llm,
            "fake/model",
            None,
            conversation_id="headless-test",
            resume=False,
        )
        try:
            await headless_runtime.engine.run("fresh")
        finally:
            await headless_runtime.close()

        assert [message.get("content") for message in non_system(headless_llm.requests[0].messages)] == ["fresh"]
    finally:
        await tui_runtime.close()

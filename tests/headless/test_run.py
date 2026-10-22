"""无头模式端到端测试 — 任务进（参数/stdin）、事件出（JSON Lines）、退出码区分成败（issue #60）。"""

from __future__ import annotations

import io
import json
import signal
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel

from src.core.plugin_host import CapabilityDeclaration, CapabilityKind, CapabilityRegistrar, Manifest
from src.headless.cli import _abort_on_sigint, exit_code, main
from src.llm.stream import Done, Error
from tests.core.engine_support import FakeLLM, text_events, tool_call_events

# ============================================================================
# 辅助
# ============================================================================


class FakePermissionPlugin:
    """注册 PERMISSION 能力的最小插件：仅用于验证 ADR 0008 警告的有无。"""

    def __init__(self) -> None:
        self.manifest = Manifest(
            name="fake-permission",
            version="0.1.0",
            api_version=1,
            capabilities=(CapabilityDeclaration(kind=CapabilityKind.PERMISSION, name="approve"),),
        )

    def register(self, registrar: CapabilityRegistrar, config: BaseModel | None) -> None:
        async def approve(call: object) -> None:
            return None

        registrar.register(CapabilityKind.PERMISSION, "approve", approve)


@dataclass(frozen=True)
class RunOutput:
    """一次 main() 调用的全部出口。"""

    code: int
    stdout: str
    stderr: str
    fake: FakeLLM

    def events(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.stdout.splitlines()]


_BASE_CONFIG = (
    "default_model: fake/model\n"
    "providers:\n"
    "  fake:\n"
    "    type: openai-compatible\n"
    "    api: http://127.0.0.1:9/v1\n"
    "    models:\n"
    "      model: {}\n"
)

_DEFAULT_CONFIG = _BASE_CONFIG + ('plugins:\n  storage:\n    config:\n      database_url: ":memory:"\n')


def _write_config(tmp_path: Path, body: str = _DEFAULT_CONFIG) -> Path:
    config_path = tmp_path / "intelliagent.yaml"
    config_path.write_text(body, encoding="utf-8")
    return config_path


def _run(
    monkeypatch: object,
    argv: list[str],
    *,
    stdin_text: str = "",
    fake: FakeLLM | None = None,
    abort: threading.Event | None = None,
) -> RunOutput:
    """经 main() 端到端跑一次无头运行：fake LLM 注入（不触网），abort 恒注入（避开信号装拆）。"""
    fake = fake if fake is not None else FakeLLM()
    monkeypatch.setattr("src.headless.cli.create_llm_client", lambda config: fake)  # type: ignore[attr-defined]
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(
        argv,
        stdin=io.StringIO(stdin_text),
        stdout=stdout,
        stderr=stderr,
        abort=abort if abort is not None else threading.Event(),
    )
    return RunOutput(code=code, stdout=stdout.getvalue(), stderr=stderr.getvalue(), fake=fake)


# ============================================================================
# 端到端：任务进、事件出
# ============================================================================


def test_argument_task_runs_to_completion_with_events(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    fake = FakeLLM()
    fake.enqueue(*tool_call_events([("call_1", "bash", json.dumps({"command": "echo headless-ok"}))]))
    fake.enqueue(*text_events("任务完成"))

    out = _run(monkeypatch, ["run", "echo一下再回答", "--config", str(config)], fake=fake)

    assert out.code == 0
    assert [event["type"] for event in out.events()] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_update",
        "message_end",
        "tool_execution_start",
        "tool_execution_end",
        "turn_end",
        "turn_start",
        "message_start",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    assert out.events()[-1] == {"type": "agent_end", "outcome": "settled"}
    observation = next(event for event in out.events() if event["type"] == "tool_execution_end")["observation"]
    assert observation["status"] == "success"  # type: ignore[index]
    assert "headless-ok" in observation["content"]  # type: ignore[index]
    assert fake.requests[0].messages[0] == {"role": "user", "content": "echo一下再回答"}
    assert any(schema["function"]["name"] == "bash" for schema in fake.requests[0].tools or [])


def test_stdin_task_drives_run_and_events_flow(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    fake = FakeLLM()
    fake.enqueue(*text_events("你好"))

    out = _run(monkeypatch, ["run", "--config", str(config)], stdin_text="介绍一下你自己\n", fake=fake)

    assert out.code == 0
    assert fake.requests[0].messages[0] == {"role": "user", "content": "介绍一下你自己"}
    assert out.events()[-1] == {"type": "agent_end", "outcome": "settled"}


# ============================================================================
# ADR 0008：无 permission 插件警告
# ============================================================================


def test_warns_on_stderr_when_no_permission_plugin(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    fake = FakeLLM()
    fake.enqueue(*text_events("done"))

    out = _run(monkeypatch, ["run", "任务", "--config", str(config)], fake=fake)

    assert out.code == 0
    assert "permission" in out.stderr
    assert "ADR 0008" in out.stderr
    assert "permission" not in out.stdout  # stdout 是纯事件流，警告只走 stderr


def test_no_warning_when_permission_plugin_installed(monkeypatch: object, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "src.runtime.plugin_assembly.builtin_plugins",
        lambda config: (FakePermissionPlugin(),),
    )  # type: ignore[attr-defined]
    config = _write_config(tmp_path)
    fake = FakeLLM()
    fake.enqueue(*text_events("done"))

    out = _run(monkeypatch, ["run", "任务", "--config", str(config)], fake=fake)

    assert out.code == 0
    assert out.stderr == ""


# ============================================================================
# 退出码区分成功与失败
# ============================================================================


def test_error_outcome_exits_nonzero(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    fake = FakeLLM()
    fake.enqueue(Error(message="boom"), Done(stop_reason="error", usage=None))

    out = _run(monkeypatch, ["run", "任务", "--config", str(config)], fake=fake)

    assert out.code == 1
    assert out.events()[-1] == {"type": "agent_end", "outcome": "error"}


def test_aborted_run_exits_nonzero(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(tmp_path)
    fake = FakeLLM()
    abort = threading.Event()
    abort.set()

    out = _run(monkeypatch, ["run", "任务", "--config", str(config)], fake=fake, abort=abort)

    assert out.code == 1
    assert out.events()[-1] == {"type": "agent_end", "outcome": "aborted"}
    assert fake.requests == []  # 中止在请求前，模型从未被调用


def test_exit_code_mapping_distinguishes_outcomes() -> None:
    assert exit_code("settled") == 0
    assert exit_code("terminated") == 0
    assert exit_code("error") == 1
    assert exit_code("aborted") == 1


def test_sigint_sets_abort_for_graceful_shutdown() -> None:
    abort = threading.Event()
    with _abort_on_sigint(abort):
        signal.raise_signal(signal.SIGINT)
    assert abort.is_set()


# ============================================================================
# 启动失败（用法 / 配置 / 插件）
# ============================================================================


def test_missing_config_file_exits_usage_code(monkeypatch: object, tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"

    out = _run(monkeypatch, ["run", "任务", "--config", str(missing)])

    assert out.code == 2
    assert str(missing) in out.stderr


def test_missing_model_exits_usage_code(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(tmp_path, "workspace:\n  dir: .\n")

    out = _run(monkeypatch, ["run", "任务", "--config", str(config)])

    assert out.code == 2
    assert "default_model" in out.stderr


def test_empty_task_exits_usage_code(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(tmp_path)

    out = _run(monkeypatch, ["run", "--config", str(config)], stdin_text="  \n")

    assert out.code == 2
    assert "任务" in out.stderr


def test_invalid_plugin_config_exits_usage_code(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(
        tmp_path,
        _BASE_CONFIG + "plugins:\n  storage:\n    config:\n      database_url: [1, 2]\n",
    )

    out = _run(monkeypatch, ["run", "任务", "--config", str(config)])

    assert out.code == 2
    assert "storage" in out.stderr


# ============================================================================
# 配置消费：plugins 段
# ============================================================================


def test_disabled_builtin_plugin_is_not_loaded(monkeypatch: object, tmp_path: Path) -> None:
    config = _write_config(
        tmp_path,
        _BASE_CONFIG
        + "plugins:\n"
        + "  basic-tools:\n"
        + "    enabled: false\n"
        + "  skill:\n"
        + "    enabled: false\n"
        + "  storage:\n"
        + "    config:\n"
        + '      database_url: ":memory:"\n',
    )
    fake = FakeLLM()
    fake.enqueue(*text_events("ok"))

    out = _run(monkeypatch, ["run", "任务", "--config", str(config)], fake=fake)

    assert out.code == 0
    assert fake.requests[0].tools is None  # basic-tools + skill 都禁用后无 Tool 能力来源


class TestReviewRegressions:
    """PR #75 审查回归：警告条件对齐 US45、诊断脱敏、零工具不警告。"""

    def test_no_warning_when_run_has_no_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """US45：run 不需要 permission 能力（零工具）时不警告。"""
        from src.core.plugin_host import PluginHost
        from src.runtime.plugin_assembly import warn_missing_permission_plugin

        stderr = io.StringIO()
        warn_missing_permission_plugin(PluginHost(), stderr)
        assert stderr.getvalue() == ""

    def test_warning_when_tools_present_without_permission(self) -> None:
        """有工具（需裁决）且无 permission 能力时警告。"""
        import io as _io

        from src.config.yaml_config import IntelliAgentConfig
        from src.runtime.plugin_assembly import build_host, warn_missing_permission_plugin

        host = build_host(IntelliAgentConfig())  # 默认内置 basic-tools
        stderr = _io.StringIO()
        warn_missing_permission_plugin(host, stderr)
        assert "permission" in stderr.getvalue()

    def test_error_output_redacts_secrets(self) -> None:
        """启动失败诊断脱敏：密钥不得经异常文本泄出。"""
        from src.runtime.plugin_assembly import redact_secrets

        text = "connect failed: url=sqlite:///db?api_key=supersecret123 token sk-abc123456789xyz"
        redacted = redact_secrets(text)
        assert "supersecret123" not in redacted
        assert "sk-abc123456789xyz" not in redacted

"""冒烟：无头模式完整组装链路（AC4 的可复核存档）。

YAML 配置 → PluginHost（内置插件）→ Engine → 真实 basic_tools 执行 → 上下文回填 → 事件流。
fake LLM 驱动（不触网），工具是真实执行的 read——链路与 PR #79 声明的冒烟一致，可复跑：
    uv run pytest tests/headless/test_smoke.py -v
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from src.headless.cli import main
from src.llm.stream import Done, TextDelta, ToolCallDelta


class SmokeLLM:
    """两步脚本：先调 read 工具，再基于真实工具结果总结。"""

    def __init__(self) -> None:
        self.step = 0

    def stream(self, request, *, abort=None):  # noqa: ANN001, ANN201
        self.step += 1
        if self.step == 1:
            yield ToolCallDelta(index=0, id="c1", name="read", arguments_delta='{"path": "README.md", "limit": 5}')
            yield Done(stop_reason="stop", usage=None)
            return
        assert any("IntelliAgent" in str(m.get("content")) for m in request.messages), "read 结果必须进入上下文"
        yield TextDelta("项目名是 IntelliAgent")
        yield Done(stop_reason="stop", usage=None)


def test_headless_smoke_completes_a_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """无头模式在工作区完成一个任务：读文件 → 上下文回填 → 总结，exit=0，事件流完整。"""
    (tmp_path / "intelliagent.yaml").write_text(
        'default_model: "smoke/model"\n'
        "providers:\n"
        "  smoke:\n"
        "    type: openai-compatible\n"
        "    api: http://127.0.0.1:9/v1\n"
        "    models:\n"
        "      model: {}\n"
        'workspace:\n  dir: "."\n',
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# IntelliAgent\n冒烟仓库\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    # cli 模块是 from-import 直接绑定，须 patch cli 侧引用（patch plugin_assembly 不生效）
    monkeypatch.setattr("src.headless.cli.create_llm_client", lambda config: SmokeLLM())

    code = main(["run", "读 README 前 5 行告诉我项目名"], abort=threading.Event())

    assert code == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    kinds = [event["type"] for event in events]
    assert "tool_execution_start" in kinds  # 真实 read 执行
    assert kinds[-1] == "agent_end" and events[-1]["outcome"] == "settled"

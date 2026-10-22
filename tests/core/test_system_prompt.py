"""System prompt 构建：固定 preamble、section 顺序、工具排序与字节稳定。"""

from __future__ import annotations

from pathlib import Path

from src.core.system_prompt import PREAMBLE, build_system_prompt


def test_prompt_starts_with_preamble_and_contains_sections(tmp_path: Path) -> None:
    prompt = build_system_prompt(tmp_path, ("bash", "read"))

    assert prompt.startswith(PREAMBLE)
    assert f"<cwd>{tmp_path.resolve()}</cwd>" in prompt
    assert "<tools>\n- bash\n- read\n</tools>" in prompt


def test_prompt_is_byte_stable_for_same_inputs(tmp_path: Path) -> None:
    first = build_system_prompt(tmp_path, ("read", "bash", "read"))
    second = build_system_prompt(tmp_path, ("bash", "read"))

    assert first == second


def test_empty_tools_omits_tools_section(tmp_path: Path) -> None:
    prompt = build_system_prompt(tmp_path, ())

    assert "<tools>" not in prompt
    assert prompt.startswith(PREAMBLE)

"""bash 工具：尾窗保留 + 超限全量落盘、超时杀进程组、非零退出码明确报错（pi-engine-principles §5）。"""

from __future__ import annotations

import shutil
import time
from typing import Any

from src.plugins.basic_tools.offload import OutputAccumulator
from src.plugins.basic_tools.procs import stream_process
from src.plugins.basic_tools.result import tool_error, tool_success
from src.plugins.basic_tools.tool import ToolSpec

DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_TIMEOUT_SECONDS = 600.0
TAIL_MAX_LINES = 2000
TAIL_MAX_CHARS = 50_000


async def run_bash(command: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> str:
    """在独立进程组中执行命令，输出尾窗进上下文、完整输出落盘可追溯。"""
    if not isinstance(command, str) or not command.strip():
        return tool_error("EMPTY_COMMAND", "command 参数为空或仅包含空格")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        return tool_error("INVALID_ARGUMENT", "timeout 必须为正数（秒）")
    shell_path = shutil.which("bash") or shutil.which("sh")
    if shell_path is None:
        return tool_error("SHELL_NOT_FOUND", "PATH 上找不到 bash/sh，无法执行命令")

    timeout = min(float(timeout), MAX_TIMEOUT_SECONDS)
    accumulator = OutputAccumulator(
        max_lines=TAIL_MAX_LINES, max_chars=TAIL_MAX_CHARS, offload_prefix="intelliagent-bash"
    )
    started = time.monotonic()
    outcome = await stream_process([shell_path, "-lc", command], timeout=timeout, sink=accumulator.feed)
    accumulator.close()

    fields: dict[str, Any] = {
        "output": accumulator.tail,
        "truncated": accumulator.truncated,
        "returncode": outcome.returncode,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    if accumulator.full_output_path is not None:
        fields["full_output_file"] = accumulator.full_output_path
    if outcome.timed_out:
        return tool_error(
            "TIMEOUT", f"命令执行超时（>{timeout:g} 秒），已终止整个进程组", timeout_seconds=timeout, **fields
        )
    if outcome.returncode != 0:
        return tool_error("COMMAND_FAILED", f"命令以退出码 {outcome.returncode} 结束", **fields)
    return tool_success(**fields)


def bash_tool() -> ToolSpec:
    return ToolSpec(
        name="bash",
        description=(
            "执行 shell 命令（bash -lc）。默认超时 30 秒，超时终止整个进程组；"
            "输出过大时只返回尾部窗口，完整输出落盘并在 full_output_file 中给出；"
            "非零退出码返回 status=error 并附 returncode。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令"},
                "timeout": {"type": "number", "description": "超时秒数，默认 30", "default": 30},
            },
            "required": ["command"],
        },
        handler=run_bash,
    )

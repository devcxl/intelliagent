"""grep 工具：ripgrep 子进程检索，匹配数 / 行宽 / 总量限额，缺失与失败均可诊断。"""

from __future__ import annotations

import functools
import shutil
from collections import deque
from typing import Any

from src.plugins.basic_tools.offload import LineSplitter
from src.plugins.basic_tools.paths import resolve_tool_path
from src.plugins.basic_tools.procs import stream_process
from src.plugins.basic_tools.result import MAX_RESULT_CHARS, tool_error, tool_success
from src.plugins.basic_tools.tool import ToolSpec
from src.utils.path_policy import PathPolicy

MAX_MATCHES = 100
MAX_LINE_CHARS = 500
GREP_TIMEOUT_SECONDS = 30.0
DIAG_LINE_LIMIT = 20


async def run_grep(pattern: str, path: str = ".", *, path_policy: PathPolicy | None = None) -> str:
    """用 ripgrep 检索：结果限额生效，任一限额命中即停止消费子进程输出。"""
    if not isinstance(pattern, str) or not pattern:
        return tool_error("EMPTY_PATTERN", "pattern 参数为空或非字符串类型")
    target, path_error = resolve_tool_path(path, path_policy)
    if path_error is not None:
        return path_error
    if target is None:
        return tool_error("PATH_RESOLVE_ERROR", f"无法解析路径: {path}")
    if not target.exists():
        return tool_error("FILE_NOT_FOUND", f"检索目标不存在: {target}", path=str(target))
    rg_path = shutil.which("rg")
    if rg_path is None:
        return tool_error(
            "RIPGREP_NOT_FOUND", "ripgrep (rg) 不在 PATH 上：请安装 ripgrep 后再使用 grep 工具", path=str(target)
        )

    matches: list[dict[str, Any]] = []
    diagnostics: deque[str] = deque(maxlen=DIAG_LINE_LIMIT)
    splitter = LineSplitter()
    collected_chars = 0
    limit_reached = False

    def sink(chunk: bytes) -> None:
        nonlocal collected_chars, limit_reached
        for line in splitter.feed(chunk):
            diagnostics.append(line)
            parsed = _parse_match_line(line)
            if parsed is None:
                continue
            file_name, line_number, text = parsed
            clipped = text[:MAX_LINE_CHARS]
            matches.append({"file": file_name, "line_number": line_number, "line": clipped})
            # 总量口径含字段开销（pi §5："整体 50KB"指序列化结果而非纯正文）
            collected_chars += len(clipped) + len(file_name) + len(str(line_number)) + 64
            if len(matches) >= MAX_MATCHES or collected_chars >= MAX_RESULT_CHARS:
                limit_reached = True
                return

    argv = [
        rg_path,
        "--no-config",
        "--with-filename",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
        "-e",
        pattern,
        "--",
        str(target),
    ]
    outcome = await stream_process(argv, timeout=GREP_TIMEOUT_SECONDS, sink=sink, stop_when=lambda: limit_reached)
    splitter.close()

    if outcome.timed_out:
        return tool_error(
            "TIMEOUT",
            f"grep 执行超时（>{GREP_TIMEOUT_SECONDS:g} 秒），已终止整个进程组",
            match_count=len(matches),
            truncated=True,
        )
    if outcome.stopped_early or outcome.returncode in (0, 1):
        # 0=有匹配，1=无匹配；两者都是正常结果。达到限额而提前终止时退出码是信号值。
        return tool_success(matches=matches, match_count=len(matches), truncated=limit_reached)
    return tool_error(
        "GREP_FAILED",
        f"ripgrep 以退出码 {outcome.returncode} 结束",
        detail="\n".join(diagnostics),
    )


def _parse_match_line(line: str) -> tuple[str, int, str] | None:
    """解析 ripgrep --no-heading 输出行 `path:line:text`；无法解析的行丢弃。"""
    parts = line.split(":", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    return parts[0], int(parts[1]), parts[2]


def grep_tool(path_policy: PathPolicy | None = None) -> ToolSpec:
    return ToolSpec(
        name="grep",
        description=(
            "在文件/目录中用正则检索内容（ripgrep 语法）。返回结构化匹配列表；"
            "最多 100 条匹配、每行 500 字符、整体 50KB，超限自动截断。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "正则表达式（ripgrep 语法）"},
                "path": {"type": "string", "description": "检索目标（文件或目录），默认当前目录", "default": "."},
            },
            "required": ["pattern"],
        },
        handler=functools.partial(run_grep, path_policy=path_policy),
    )

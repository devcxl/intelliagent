"""read / write / edit 工具：分页续读、不回灌文件、精确匹配只回 diff（pi-engine-principles §5）。"""

from __future__ import annotations

import difflib
import functools

from src.plugins.basic_tools.paths import resolve_tool_path
from src.plugins.basic_tools.result import MAX_RESULT_CHARS, tool_error, tool_success
from src.plugins.basic_tools.tool import ToolSpec
from src.utils.path_policy import PathPolicy

MAX_READ_LINES = 2000
MAX_WRITE_CHARS = 1_000_000
CONTINUATION_NOTE = "[Showing lines {start}-{end} of {total}. Use offset={next_offset} to continue.]"


async def run_read(
    path: str, offset: int = 1, limit: int = MAX_READ_LINES, *, path_policy: PathPolicy | None = None
) -> str:
    """分页读取文件：窗口受行数与字符预算双重限制，超限返回续读提示，绝不整文件回灌。"""
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 1:
        return tool_error("INVALID_ARGUMENT", "offset 必须为 ≥ 1 的整数")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return tool_error("INVALID_ARGUMENT", "limit 必须为 ≥ 1 的整数")
    file_path, path_error = resolve_tool_path(path, path_policy)
    if path_error is not None:
        return path_error
    if file_path is None:
        return tool_error("PATH_RESOLVE_ERROR", f"无法解析路径: {path}")
    if not file_path.exists():
        return tool_error("FILE_NOT_FOUND", f"文件不存在: {file_path}", path=str(file_path))
    if file_path.is_dir():
        return tool_error("IS_DIRECTORY", f"路径是目录而非文件: {file_path}", path=str(file_path))

    # 单遍流式读取：只保留窗口内容，总行数边读边计，内存 O(窗口) 而非 O(文件)。
    lines_in_window: list[str] = []
    total_lines = 0
    end_line = offset - 1
    line_cut = False
    window_exhausted = False
    end_candidate = offset - 1 + min(limit, MAX_READ_LINES)
    used = 0
    with file_path.open(encoding="utf-8", errors="replace") as handle:
        for index, raw_line in enumerate(handle, start=1):
            total_lines = index
            if index < offset or window_exhausted:
                continue
            line = raw_line.rstrip("\n")
            if index > end_candidate:
                window_exhausted = True
                continue
            extra = len(line) + (1 if lines_in_window else 0)
            if used + extra > MAX_RESULT_CHARS:
                if not lines_in_window:
                    lines_in_window.append(line[:MAX_RESULT_CHARS])
                    end_line += 1
                    line_cut = True
                window_exhausted = True
                continue
            lines_in_window.append(line)
            used += extra
            end_line += 1

    if total_lines == 0:
        if offset != 1:
            return tool_error("OFFSET_OUT_OF_RANGE", f"offset {offset} 超出文件行数 0", total_lines=0)
        return tool_success(
            path=str(file_path), content="", start_line=1, end_line=0, total_lines=0, truncated=False, note=""
        )
    if offset > total_lines:
        return tool_error("OFFSET_OUT_OF_RANGE", f"offset {offset} 超出文件行数 {total_lines}", total_lines=total_lines)

    selected = lines_in_window

    notes: list[str] = []
    if line_cut:
        notes.append(f"[Line {end_line} truncated to {MAX_RESULT_CHARS} chars.]")
    if end_line < total_lines:
        notes.append(CONTINUATION_NOTE.format(start=offset, end=end_line, total=total_lines, next_offset=end_line + 1))
    return tool_success(
        path=str(file_path),
        content="\n".join(selected),
        start_line=offset,
        end_line=end_line,
        total_lines=total_lines,
        truncated=end_line < total_lines or line_cut,
        note="\n".join(notes),
    )


async def run_write(path: str, content: str, *, path_policy: PathPolicy | None = None) -> str:
    """写入文件：只返回成功消息，绝不回灌文件内容（pi 输出纪律）。"""
    if not isinstance(content, str):
        return tool_error("INVALID_ARGUMENT", "content 必须为字符串")
    if len(content) > MAX_WRITE_CHARS:
        return tool_error("CONTENT_TOO_LARGE", f"内容过大（{len(content)} > {MAX_WRITE_CHARS} 字符）", path=str(path))
    file_path, path_error = resolve_tool_path(path, path_policy)
    if path_error is not None:
        return path_error
    if file_path is None:
        return tool_error("PATH_RESOLVE_ERROR", f"无法解析路径: {path}")
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return tool_error("WRITE_ERROR", f"写入文件失败: {exc}", path=str(file_path))
    return tool_success(message="文件已写入", path=str(file_path), chars=len(content))


async def run_edit(
    path: str,
    oldString: str,
    newString: str,
    replaceAll: bool = False,
    *,
    path_policy: PathPolicy | None = None,
) -> str:
    """精确替换文件内容：匹配不做任何空白归一化，只返回 diff，绝不回灌全文。"""
    if not isinstance(oldString, str) or oldString == "":
        return tool_error("EMPTY_OLD_STRING", "oldString 不能为空（空串会匹配任意位置）")
    if not isinstance(newString, str):
        return tool_error("INVALID_ARGUMENT", "newString 必须为字符串")
    if not isinstance(replaceAll, bool):
        return tool_error("INVALID_ARGUMENT", "replaceAll 必须为布尔值")
    if oldString == newString:
        return tool_error("IDENTICAL_STRINGS", "oldString 与 newString 相同，替换没有效果")
    file_path, path_error = resolve_tool_path(path, path_policy)
    if path_error is not None:
        return path_error
    if file_path is None:
        return tool_error("PATH_RESOLVE_ERROR", f"无法解析路径: {path}")
    if not file_path.exists():
        return tool_error("FILE_NOT_FOUND", f"文件不存在: {file_path}", path=str(file_path))
    if file_path.is_dir():
        return tool_error("IS_DIRECTORY", f"路径是目录而非文件: {file_path}", path=str(file_path))

    content = file_path.read_text(encoding="utf-8", errors="replace")
    matches = content.count(oldString)
    if matches == 0:
        return tool_error("OLD_STRING_NOT_FOUND", "未找到 oldString：请提供与文件内容完全一致（含空白）的片段")
    if matches > 1 and not replaceAll:
        return tool_error(
            "MULTIPLE_MATCHES",
            f"找到 {matches} 处匹配：请设置 replaceAll=true 或提供更精确的 oldString",
            matches=matches,
        )

    new_content = content.replace(oldString, newString) if replaceAll else content.replace(oldString, newString, 1)
    if len(new_content) > MAX_WRITE_CHARS:
        return tool_error("CONTENT_TOO_LARGE", f"编辑后内容过大（{len(new_content)} > {MAX_WRITE_CHARS} 字符）")
    try:
        file_path.write_text(new_content, encoding="utf-8")
    except OSError as exc:
        return tool_error("WRITE_ERROR", f"写入文件失败: {exc}", path=str(file_path))

    diff = "".join(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(file_path),
            tofile=str(file_path),
        )
    )
    truncated = len(diff) > MAX_RESULT_CHARS
    if truncated:
        diff = diff[:MAX_RESULT_CHARS]
    return tool_success(
        message="文件已编辑",
        path=str(file_path),
        replacements=matches if replaceAll else 1,
        diff=diff,
        truncated=truncated,
    )


def read_tool(path_policy: PathPolicy | None = None) -> ToolSpec:
    return ToolSpec(
        name="read",
        description=(
            "读取文件内容（按行分页）。offset 为起始行号（1 起），limit 为返回行数（默认 2000）；"
            "超出窗口时按返回提示用 offset 续读，不会返回整个文件。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "offset": {"type": "integer", "description": "起始行号（1 起），默认 1", "default": 1},
                "limit": {"type": "integer", "description": "返回行数上限，默认 2000", "default": 2000},
            },
            "required": ["path"],
        },
        handler=functools.partial(run_read, path_policy=path_policy),
    )


def write_tool(path_policy: PathPolicy | None = None) -> ToolSpec:
    return ToolSpec(
        name="write",
        description="写入文件内容（覆盖写，自动创建父目录）。成功时不回显文件内容。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "content": {"type": "string", "description": "文件内容"},
            },
            "required": ["path", "content"],
        },
        handler=functools.partial(run_write, path_policy=path_policy),
    )


def edit_tool(path_policy: PathPolicy | None = None) -> ToolSpec:
    return ToolSpec(
        name="edit",
        description=(
            "编辑文件内容：把 oldString 精确替换为 newString（空白敏感，不做归一化）。"
            "多处匹配时必须设置 replaceAll=true，否则报错；结果只返回 diff。"
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"},
                "oldString": {"type": "string", "description": "要替换的旧字符串（必须与文件内容完全一致）"},
                "newString": {"type": "string", "description": "替换后的新字符串"},
                "replaceAll": {
                    "type": "boolean",
                    "description": "是否替换所有匹配（默认 false，多匹配时报错）",
                    "default": False,
                },
            },
            "required": ["path", "oldString", "newString"],
        },
        handler=functools.partial(run_edit, path_policy=path_policy),
    )

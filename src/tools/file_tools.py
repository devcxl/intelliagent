import pathlib

from src.utils.logger import logger
from src.utils.path_policy import PathPolicy
from src.utils.path_utils import resolve_workspace_root

from .response import error_response, success_response

try:
    import aiofiles

    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

FILE_READ_MAX_SIZE = 50000  # 文件读取最大字符数
FILE_WRITE_MAX_SIZE = 1000000  # 文件写入最大字符数（1MB）


def _validate_path_arg(path: str) -> tuple[str | None, str | None]:
    if not path or not isinstance(path, str):
        return None, error_response("path 参数为空或非字符串类型", "EMPTY_PATH")
    path = path.strip()
    if not path:
        return None, error_response("path 参数为空或仅包含空格", "EMPTY_PATH")
    return path, None


def _check_workspace_boundary(
    file_path: pathlib.Path, workspace_root: str | None = None, path_policy: PathPolicy | None = None
) -> str | None:
    if path_policy is not None:
        result = path_policy.check(str(file_path))
        if not result.allowed_by_boundary:
            return error_response(
                f"路径超出工作区范围: {file_path.resolve()} (工作区: {path_policy.workspace})",
                "PATH_OUTSIDE_WORKSPACE",
            )
        return None
    ws = resolve_workspace_root(workspace_root)
    if ws is None:
        return None
    try:
        resolved = file_path.resolve()
    except (OSError, RuntimeError):
        return error_response(f"无法解析路径: {file_path}", "PATH_RESOLVE_ERROR")
    resolved_str = str(resolved)
    from src.utils.path_policy import PathPolicy as _PP

    if not _PP(workspace=ws).check(resolved_str).allowed_by_boundary:
        return error_response(
            f"路径超出工作区范围: {resolved} (工作区: {ws})",
            "PATH_OUTSIDE_WORKSPACE",
        )
    return None


async def read_file(path: str, workspace_root: str | None = None, path_policy: PathPolicy | None = None) -> str:
    """异步读取文件内容。

    支持工作区边界检查、文件大小截断，优先使用 aiofiles 异步读取。

    Args:
        path: 文件路径，支持 ~ 展开
        workspace_root: 工作区根路径，用于边界检查，None 时从环境变量获取
        path_policy: 路径边界策略，优先于 workspace_root

    Returns:
        JSON 格式的响应，成功时包含 content、size、truncated、path 字段
    """
    stripped_path, error = _validate_path_arg(path)
    if error is not None:
        return error
    assert stripped_path is not None

    try:
        file_path = pathlib.Path(stripped_path).expanduser()

        boundary_error = _check_workspace_boundary(file_path, workspace_root, path_policy)
        if boundary_error is not None:
            return boundary_error

        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")

        if file_path.is_dir():
            return error_response(f"路径是目录而非文件: {path}", "IS_DIRECTORY")

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
                content = await f.read()
        else:
            content = file_path.read_text(encoding="utf-8")

        truncated = False
        if len(content) > FILE_READ_MAX_SIZE:
            content = content[:FILE_READ_MAX_SIZE]
            truncated = True

        logger.debug("FileTools - 读取文件 | path=%s size=%d", str(file_path), len(content))

        return success_response(
            {"content": content, "size": len(content), "truncated": truncated, "path": str(file_path)}
        )

    except Exception as e:
        return error_response(f"读取文件失败: {str(e)}", "READ_ERROR")


async def write_file(
    path: str, content: str, workspace_root: str | None = None, path_policy: PathPolicy | None = None
) -> str:
    """异步写入文件内容。

    自动创建父目录，支持工作区边界检查，优先使用 aiofiles 异步写入。

    Args:
        path: 文件路径，支持 ~ 展开
        content: 要写入的文件内容
        workspace_root: 工作区根路径，用于边界检查，None 时从环境变量获取
        path_policy: 路径边界策略，优先于 workspace_root

    Returns:
        JSON 格式的响应，成功时包含 message、path、size 字段
    """
    stripped_path, error = _validate_path_arg(path)
    if error is not None:
        return error
    assert stripped_path is not None

    if content is None:
        return error_response("content 参数为空", "EMPTY_CONTENT")

    if not isinstance(content, str):
        content = str(content)

    if len(content) > FILE_WRITE_MAX_SIZE:
        return error_response(
            f"内容过大（{len(content)} > {FILE_WRITE_MAX_SIZE} 字符），超过 1MB 限制", "CONTENT_TOO_LARGE"
        )

    try:
        file_path = pathlib.Path(stripped_path).expanduser()

        boundary_error = _check_workspace_boundary(file_path, workspace_root, path_policy)
        if boundary_error is not None:
            return boundary_error

        file_path.parent.mkdir(parents=True, exist_ok=True)

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode="w", encoding="utf-8") as f:
                await f.write(content)
        else:
            file_path.write_text(content, encoding="utf-8")

        logger.debug("FileTools - 写入文件 | path=%s size=%d", str(file_path), len(content))

        return success_response({"message": "文件已创建", "path": str(file_path), "size": len(content)})

    except Exception as e:
        return error_response(f"写入文件失败: {str(e)}", "WRITE_ERROR")


async def edit_file(
    path: str,
    oldString: str,
    newString: str,
    replaceAll: bool = False,
    workspace_root: str | None = None,
    path_policy: PathPolicy | None = None,
) -> str:
    """异步编辑文件内容，精确替换指定字符串。

    支持单次替换和全部替换两种模式，替换后自动写回文件。

    Args:
        path: 文件路径，支持 ~ 展开
        oldString: 要替换的旧字符串
        newString: 替换后的新字符串
        replaceAll: 是否替换所有匹配项，默认 False（仅替换首次出现）
        workspace_root: 工作区根路径，用于边界检查，None 时从环境变量获取
        path_policy: 路径边界策略，优先于 workspace_root

    Returns:
        JSON 格式的响应，成功时包含 message、replacements、content、path、size 字段
    """
    stripped_path, error = _validate_path_arg(path)
    if error is not None:
        return error
    assert stripped_path is not None

    if not oldString or not isinstance(oldString, str):
        return error_response("oldString 参数为空或非字符串类型", "EMPTY_OLD_STRING")

    oldString = oldString.strip()
    if not oldString:
        return error_response("oldString 参数为空或仅包含空格", "EMPTY_OLD_STRING")

    if newString is None:
        newString = ""

    try:
        file_path = pathlib.Path(stripped_path).expanduser()

        boundary_error = _check_workspace_boundary(file_path, workspace_root, path_policy)
        if boundary_error is not None:
            return boundary_error

        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")

        if file_path.is_dir():
            return error_response(f"路径是目录而非文件: {path}", "IS_DIRECTORY")

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode="r", encoding="utf-8") as f:
                content = await f.read()
        else:
            content = file_path.read_text(encoding="utf-8")

        occurrence_count = content.count(oldString)

        if occurrence_count == 0:
            return error_response("未找到要替换的文本片段，请检查 oldString 是否正确", "OLD_STRING_NOT_FOUND")

        if occurrence_count > 1 and not replaceAll:
            msg = (
                f"找到 {occurrence_count} 处匹配，但 replaceAll=False，"
                "仅允许单次替换。请设置 replaceAll=True 或提供更精确的 oldString。"
            )
            return error_response(msg, "MULTIPLE_MATCHES")

        if replaceAll:
            new_content = content.replace(oldString, newString)
        else:
            new_content = content.replace(oldString, newString, 1)

        if len(new_content) > FILE_WRITE_MAX_SIZE:
            return error_response(
                f"编辑后内容过大（{len(new_content)} > {FILE_WRITE_MAX_SIZE} 字符），超过 1MB 限制", "CONTENT_TOO_LARGE"
            )

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode="w", encoding="utf-8") as f:
                await f.write(new_content)
        else:
            file_path.write_text(new_content, encoding="utf-8")

        preview_length = 500
        content_preview = new_content[:preview_length]
        if len(new_content) > preview_length:
            content_preview += "..."

        replacements = occurrence_count if replaceAll else 1
        logger.debug("FileTools - 编辑文件 | path=%s replacements=%d", str(file_path), replacements)

        return success_response(
            {
                "message": "文件编辑成功",
                "replacements": replacements,
                "content": content_preview,
                "path": str(file_path),
                "size": len(new_content),
            }
        )

    except Exception as e:
        return error_response(f"编辑文件失败: {str(e)}", "WRITE_ERROR")

import pathlib
from .response import success_response, error_response
from src.utils.logger import logger

try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

FILE_READ_MAX_SIZE = 50000
FILE_WRITE_MAX_SIZE = 1000000


async def read_file(path: str) -> str:
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")

    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")

    try:
        file_path = pathlib.Path(path).expanduser()

        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")

        if file_path.is_dir():
            return error_response(f"路径是目录而非文件: {path}", "IS_DIRECTORY")

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
        else:
            content = file_path.read_text(encoding='utf-8')

        truncated = False
        if len(content) > FILE_READ_MAX_SIZE:
            content = content[:FILE_READ_MAX_SIZE]
            truncated = True

        logger.debug("FileTools - 读取文件 | path=%s size=%d", str(file_path), len(content))

        return success_response({
            "content": content,
            "size": len(content),
            "truncated": truncated,
            "path": str(file_path)
        })

    except Exception as e:
        return error_response(f"读取文件失败: {str(e)}", "READ_ERROR")


async def write_file(path: str, content: str) -> str:
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")

    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")

    if content is None:
        return error_response("content 参数为空", "EMPTY_CONTENT")

    if not isinstance(content, str):
        content = str(content)

    if len(content) > FILE_WRITE_MAX_SIZE:
        return error_response(
            f"内容过大（{len(content)} > {FILE_WRITE_MAX_SIZE} 字符），超过 1MB 限制",
            "CONTENT_TOO_LARGE"
        )

    try:
        file_path = pathlib.Path(path).expanduser()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
                await f.write(content)
        else:
            file_path.write_text(content, encoding='utf-8')

        logger.debug("FileTools - 写入文件 | path=%s size=%d", str(file_path), len(content))

        return success_response({
            "message": "文件已创建",
            "path": str(file_path),
            "size": len(content)
        })

    except Exception as e:
        return error_response(f"写入文件失败: {str(e)}", "WRITE_ERROR")


async def edit_file(path: str, oldString: str, newString: str, replaceAll: bool = False) -> str:
    if not path or not isinstance(path, str):
        return error_response("path 参数为空或非字符串类型", "EMPTY_PATH")

    path = path.strip()
    if not path:
        return error_response("path 参数为空或仅包含空格", "EMPTY_PATH")

    if not oldString or not isinstance(oldString, str):
        return error_response("oldString 参数为空或非字符串类型", "EMPTY_OLD_STRING")

    oldString = oldString.strip()
    if not oldString:
        return error_response("oldString 参数为空或仅包含空格", "EMPTY_OLD_STRING")

    if newString is None:
        newString = ""

    try:
        file_path = pathlib.Path(path).expanduser()

        if not file_path.exists():
            return error_response(f"文件不存在: {path}", "FILE_NOT_FOUND")

        if file_path.is_dir():
            return error_response(f"路径是目录而非文件: {path}", "IS_DIRECTORY")

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='r', encoding='utf-8') as f:
                content = await f.read()
        else:
            content = file_path.read_text(encoding='utf-8')

        occurrence_count = content.count(oldString)

        if occurrence_count == 0:
            return error_response(
                f"未找到要替换的文本片段，请检查 oldString 是否正确",
                "OLD_STRING_NOT_FOUND"
            )

        if occurrence_count > 1 and not replaceAll:
            return error_response(
                f"找到 {occurrence_count} 处匹配，但 replaceAll=False，仅允许单次替换。请设置 replaceAll=True 或提供更精确的 oldString。",
                "MULTIPLE_MATCHES"
            )

        if replaceAll:
            new_content = content.replace(oldString, newString)
        else:
            new_content = content.replace(oldString, newString, 1)

        if len(new_content) > FILE_WRITE_MAX_SIZE:
            return error_response(
                f"编辑后内容过大（{len(new_content)} > {FILE_WRITE_MAX_SIZE} 字符），超过 1MB 限制",
                "CONTENT_TOO_LARGE"
            )

        if HAS_AIOFILES:
            async with aiofiles.open(file_path, mode='w', encoding='utf-8') as f:
                await f.write(new_content)
        else:
            file_path.write_text(new_content, encoding='utf-8')

        preview_length = 500
        content_preview = new_content[:preview_length]
        if len(new_content) > preview_length:
            content_preview += "..."

        replacements = occurrence_count if replaceAll else 1
        logger.debug("FileTools - 编辑文件 | path=%s replacements=%d", str(file_path), replacements)

        return success_response({
            "message": "文件编辑成功",
            "replacements": replacements,
            "content": content_preview,
            "path": str(file_path),
            "size": len(new_content)
        })

    except Exception as e:
        return error_response(f"编辑文件失败: {str(e)}", "WRITE_ERROR")

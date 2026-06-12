import asyncio
import shutil
import time

from src.utils.logger import logger

from .response import error_response, success_response

SHELL_COMMAND_TIMEOUT = 30


async def run_shell(cmd: str) -> str:
    if not cmd or not isinstance(cmd, str):
        return error_response("cmd 参数为空或非字符串类型", "EMPTY_COMMAND")

    cmd = cmd.strip()
    if not cmd:
        return error_response("cmd 参数为空或仅包含空格", "EMPTY_COMMAND")

    try:
        start_time = time.monotonic()
        bash_path = shutil.which("bash")
        if bash_path:
            process = await asyncio.create_subprocess_exec(
                bash_path,
                "-lc",
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        else:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=SHELL_COMMAND_TIMEOUT
            )
        except asyncio.TimeoutError:
            process.kill()
            return error_response(
                f"命令执行超时（>{SHELL_COMMAND_TIMEOUT}秒）",
                "TIMEOUT"
            )

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        logger.debug(
            "ShellTool - 执行命令 | cmd=%s time_ms=%d returncode=%d",
            cmd, elapsed_ms, process.returncode
        )

        output = stdout.decode('utf-8', errors='replace').strip()
        error_output = stderr.decode('utf-8', errors='replace').strip()

        full_output = output
        if error_output and process.returncode != 0:
            full_output = f"{output}\n{error_output}".strip()

        return success_response({
            "output": full_output,
            "returncode": process.returncode
        })

    except Exception as e:
        return error_response(f"命令执行失败: {str(e)}", "EXECUTION_ERROR")

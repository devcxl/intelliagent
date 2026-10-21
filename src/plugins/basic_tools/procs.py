"""子进程执行：独立进程组 + 超时 killpg + 流式输出，供 bash / grep 共用。"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from collections.abc import Callable, Sequence
from typing import NamedTuple

CHUNK_SIZE = 65536
DRAIN_TIMEOUT_SECONDS = 2.0
DRAIN_READ_TIMEOUT_SECONDS = 0.2


class ProcessOutcome(NamedTuple):
    """一次子进程执行的收敛结果。"""

    returncode: int
    timed_out: bool
    stopped_early: bool


def kill_process_group(process: asyncio.subprocess.Process) -> None:
    """SIGKILL 整个进程组（配合 start_new_session），进程已退出时静默返回。

    注意：pgid 必须用 spawn 时固化的 pid（start_new_session 下子进程即组长），
    不能运行时 getpgid——直接子进程被 reaped 后 getpgid 抛 ProcessLookupError
    会静默跳过 kill，同组孙进程存活（US13：不得留孤儿进程）。
    """
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # 进程组已消失


async def stream_process(
    argv: Sequence[str],
    *,
    timeout: float,
    sink: Callable[[bytes], None],
    stop_when: Callable[[], bool] | None = None,
) -> ProcessOutcome:
    """在独立进程组中执行 argv，把 stdout（含 stderr）流式喂给 sink。

    超时或 stop_when 命中时 kill 整个进程组（不留下孤儿进程）；
    超时后短暂排干管道，尽量把已产生的输出交给 sink。
    """
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    stdout = process.stdout
    if stdout is None:  # create_subprocess_exec 在 PIPE 下不会发生；仅为收窄类型
        raise RuntimeError("子进程 stdout 未接通")
    deadline = time.monotonic() + timeout
    timed_out = False
    stopped_early = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            try:
                chunk = await asyncio.wait_for(stdout.read(CHUNK_SIZE), timeout=remaining)
            except asyncio.TimeoutError:
                timed_out = True
                break
            if not chunk:
                break
            sink(chunk)
            if stop_when is not None and stop_when():
                stopped_early = True
                break
        if timed_out:
            kill_process_group(process)
            await _drain(stdout, sink)
    finally:
        if process.returncode is None:
            kill_process_group(process)
        await process.wait()
    return ProcessOutcome(process.returncode if process.returncode is not None else 0, timed_out, stopped_early)


async def _drain(stdout: asyncio.StreamReader, sink: Callable[[bytes], None]) -> None:
    """kill 后在有限时间内排干管道，读到 EOF 或预算耗尽即返回。"""
    deadline = time.monotonic() + DRAIN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            chunk = await asyncio.wait_for(stdout.read(CHUNK_SIZE), timeout=DRAIN_READ_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            return
        if not chunk:
            return
        sink(chunk)

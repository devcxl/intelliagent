"""无头模式入口（CONTEXT 术语：Headless Mode）：任务进、事件流出、退出码区分成败。

用法::

    intelliagent run "任务"              # 任务参数进
    echo "任务" | intelliagent run       # stdin 进
    python -m src.headless run "任务"    # 免安装形态

stdout 是 JSON Lines 事件流（src.headless.events），stderr 是人类可读诊断——含 ADR 0008 的
"无 permission 插件"安全警告。退出码：0 收束成功（settled / terminated），1 运行失败
（error / aborted），2 启动失败（用法 / 配置 / 插件错误）。首个 SIGINT 置位 abort 让引擎在
turn 边界优雅收束（outcome=aborted），第二个 SIGINT 恢复默认行为强制中断。
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
import threading
from collections.abc import Iterator, Sequence
from types import FrameType
from typing import TextIO

from src.config.yaml_config import ConfigError, load_config
from src.core.agent_events import RunOutcome
from src.core.engine import Engine
from src.core.plugin_host import PluginError, PluginHost
from src.headless.events import JsonLineSink
from src.runtime.plugin_assembly import build_host, create_llm_client, redact_secrets, warn_missing_permission_plugin

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2


def exit_code(outcome: RunOutcome) -> int:
    """RunOutcome → 退出码：settled/terminated 是成功收束（含工具显式终止），error/aborted 是失败。"""
    return EXIT_OK if outcome in ("settled", "terminated") else EXIT_FAILURE


def build_parser() -> argparse.ArgumentParser:
    """argparse 解析：run 子命令 + 任务位置参数（缺省读 stdin）+ --config。"""
    parser = argparse.ArgumentParser(prog="intelliagent", description="IntelliAgent 无头模式：任务进、事件流出")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="执行一个任务，事件流以 JSON Lines 写到 stdout")
    run.add_argument("task", nargs="?", help="任务内容；缺省时从 stdin 读取")
    run.add_argument("--config", help="intelliagent.yaml 路径（默认当前目录的 intelliagent.yaml）")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    abort: threading.Event | None = None,
) -> int:
    """无头执行入口：解析任务 → 装配运行时 → 跑 Run → 事件流出 → 退出码。

    stdin/stdout/stderr/abort 均可注入（测试不碰进程全局状态）；abort 缺省时才装 SIGINT 处理。
    长 LLM 流/长工具执行期间 Ctrl-C 不即时生效（abort 粒度是 turn 边界，见 engine 文档）；
    双击 Ctrl-C 走 SIG_DFL 强杀。
    """
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    args = build_parser().parse_args(argv)
    assembled = _assemble(args, stdin, stdout, stderr)
    if isinstance(assembled, int):
        return assembled
    host, engine, task = assembled
    warn_missing_permission_plugin(host, stderr)
    if abort is not None:
        return _run(engine, task, abort, stderr)
    own_abort = threading.Event()
    with _abort_on_sigint(own_abort):
        return _run(engine, task, own_abort, stderr)


def _assemble(
    args: argparse.Namespace, stdin: TextIO, stdout: TextIO, stderr: TextIO
) -> tuple[PluginHost, Engine, str] | int:
    """解析任务 → 加载配置 → 组装 PluginHost 与 Engine；启动失败统一走脱敏错误输出并返回退出码。"""
    try:
        task = _resolve_task(args.task, stdin)
        config = load_config(args.config)
        if not config.default_model:
            raise ValueError("配置缺少 default_model（如 deepseek/deepseek-flash）")
        client = create_llm_client(config)
        host = build_host(config)
    except (ValueError, ConfigError, PluginError) as exc:
        return _fail(stderr, exc)
    engine = Engine.from_host(host, llm=client, model=config.default_model, sink=JsonLineSink(stdout))
    return host, engine, task


def _fail(stderr: TextIO, exc: Exception) -> int:
    """统一启动失败输出：脱敏后写 stderr（密钥不得经异常文本泄出）。"""
    stderr.write(f"error: {redact_secrets(str(exc))}\n")
    return EXIT_USAGE


def _run(engine: Engine, task: str, abort: threading.Event, stderr: TextIO) -> int:
    """跑一个 Run 并把收束结果映射为退出码；运行期异常收敛为失败退出。"""
    try:
        result = asyncio.run(engine.run(task, abort=abort))
    except Exception as exc:
        stderr.write(f"error: {redact_secrets(str(exc))}\n")
        return EXIT_FAILURE
    return exit_code(result.outcome)


def _resolve_task(argument: str | None, stdin: TextIO) -> str:
    """任务来源：位置参数优先，缺省读 stdin；两端都为空给出可诊断错误。"""
    text = argument if argument is not None else stdin.read()
    task = text.strip()
    if not task:
        raise ValueError("任务为空：请提供任务参数，或经 stdin 传入任务内容")
    return task


@contextlib.contextmanager
def _abort_on_sigint(abort: threading.Event) -> Iterator[None]:
    """SIGINT 处理：首个 Ctrl-C 置位 abort（引擎在 turn 边界收束为 aborted），恢复默认 handler 退出。

    非主线程装不了信号 handler，退化为普通运行（abort 仍可由调用方注入）。
    """

    def _handler(signum: int, frame: FrameType | None) -> None:
        abort.set()
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    try:
        previous = signal.signal(signal.SIGINT, _handler)
    except ValueError:
        yield
        return
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
